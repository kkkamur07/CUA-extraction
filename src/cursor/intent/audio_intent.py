"""Audio → intent pipeline (orthogonal to the keypress pipeline).

Stages:
  1. extract    — pull the audio track out of the video as mono 16 kHz WAV
                  chunks (bundled ffmpeg via imageio-ffmpeg, no system install)
  2. transcribe — speech-to-text per chunk with segment timestamps,
                  offset back to absolute video time
  3. summarize  — LLM turns the transcript into standardized intent intervals
                  (ACTION = observable "I'll ...", INTENT = immediate "I need
                  to ..." purpose, hedged with "likely" when inferred), plus a
                  task-level summary

Providers are injected via cursor.intent.providers — swap with env config.
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg

from . import providers
from .providers.base import TranscriptSegment

INTENT_SYSTEM = """You convert tutorial narration transcripts into standardized intent annotations for computer-use training data.

You receive transcript segments as lines "START-END: text" (seconds). Partition the covered time span into consecutive, non-overlapping intervals that follow the speaker's workflow phases (typically 5-30 seconds each). Interval boundaries MUST coincide with transcript segment boundaries.

For each interval output:
- "action": first person, future tense — the observable thing being done, e.g. "I'll sketch a rectangle on the front plane and dimension it."
- "intent": first person — the immediate purpose one level above the action, e.g. "I need to create the base profile for the part." If the purpose is inferred rather than stated, hedge it with "likely".
- "quote": a short verbatim snippet from the transcript that supports the annotation.

Merge filler / small talk into the neighboring interval. Cover all speech.
Reply with ONLY a JSON object: {"intervals": [{"start_t": number, "end_t": number, "action": string, "intent": string, "quote": string}]}"""

SUMMARY_SYSTEM = """You summarize a tutorial workflow for computer-use training data.
Given intent annotations of the whole session, write a first-person task "summary" paragraph narrating the workflow from start to finish (what is done and why, 3-6 sentences, style: "I need to ... I'll ... Finally, I'll ...").
Reply with ONLY a JSON object: {"summary": string}"""


@dataclass
class AudioJob:
    video_path: str
    duration: float
    chunk_s: int = 600
    language: str | None = None

    state: str = "pending"     # extracting | transcribing | summarizing | done | error
    progress: float = 0.0
    error: str = ""
    transcript: list[TranscriptSegment] = field(default_factory=list)
    intents: list[dict] = field(default_factory=list)
    task_summary: str = ""
    doc: dict | None = None


def _extract_chunks(job: AudioJob, workdir: Path) -> list[tuple[float, Path]]:
    """WAV chunk per chunk_s window. Returns [(start_offset_s, path)]."""
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    n = max(1, math.ceil(job.duration / job.chunk_s))
    chunks = []
    for i in range(n):
        start = i * job.chunk_s
        out = workdir / f"chunk_{i:03d}.wav"
        cmd = [exe, "-y", "-v", "error",
               "-ss", str(start), "-t", str(job.chunk_s),
               "-i", job.video_path,
               "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(out)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if p.returncode != 0 or not out.exists() or out.stat().st_size < 128:
            err = (p.stderr or "").strip()
            if i == 0:
                raise RuntimeError(
                    f"could not extract audio — does the video have an audio track? ffmpeg: {err[:300]}")
            break  # ran past the end
        chunks.append((float(start), out))
        job.progress = 0.15 * (i + 1) / n
    return chunks


def _windows(segs: list[TranscriptSegment], max_segs=80, max_span=900.0):
    """Split transcript into LLM-sized windows at segment boundaries."""
    win, span_start = [], None
    for s in segs:
        if win and (len(win) >= max_segs or s.end_t - span_start > max_span):
            yield win
            win, span_start = [], None
        if span_start is None:
            span_start = s.start_t
        win.append(s)
    if win:
        yield win


def _fmt_transcript(segs: list[TranscriptSegment]) -> str:
    return "\n".join(f"{s.start_t:.1f}-{s.end_t:.1f}: {s.text}" for s in segs)


def _valid_intervals(raw, t_lo: float, t_hi: float) -> list[dict]:
    """Validate/clean what the model returned."""
    out = []
    for iv in raw if isinstance(raw, list) else []:
        try:
            a, b = float(iv["start_t"]), float(iv["end_t"])
        except (KeyError, TypeError, ValueError):
            continue
        if b <= a:
            continue
        out.append({
            "start_t": round(max(a, t_lo), 3),
            "end_t": round(min(b, t_hi), 3),
            "action": str(iv.get("action", "")).strip(),
            "intent": str(iv.get("intent", "")).strip(),
            "quote": str(iv.get("quote", "")).strip(),
        })
    out.sort(key=lambda x: x["start_t"])
    return out


def run(job: AudioJob):
    try:
        transcriber = providers.get_transcriber()
        llm = providers.get_intent_model()

        job.state = "extracting"
        with tempfile.TemporaryDirectory(prefix="kps_audio_") as td:
            workdir = Path(td)
            chunks = _extract_chunks(job, workdir)

            job.state = "transcribing"
            segs: list[TranscriptSegment] = []
            for i, (offset, wav) in enumerate(chunks):
                for s in transcriber.transcribe(str(wav), job.language):
                    segs.append(TranscriptSegment(s.start_t + offset, s.end_t + offset, s.text))
                job.progress = 0.15 + 0.55 * (i + 1) / len(chunks)
        segs.sort(key=lambda s: s.start_t)
        job.transcript = segs
        if not segs:
            raise RuntimeError("no speech found in the audio track")

        job.state = "summarizing"
        intents: list[dict] = []
        wins = list(_windows(segs))
        for i, win in enumerate(wins):
            user = _fmt_transcript(win)
            if intents:
                tail = intents[-2:]
                user = ("Context — the previous annotated intervals were:\n"
                        + json.dumps(tail, indent=0) + "\n\nTranscript to annotate:\n" + user)
            res = llm.complete_json(INTENT_SYSTEM, user)
            intents.extend(_valid_intervals(res.get("intervals"), win[0].start_t, win[-1].end_t))
            job.progress = 0.70 + 0.25 * (i + 1) / len(wins)

        if not intents:
            raise RuntimeError("intent model returned no intervals")
        res = llm.complete_json(SUMMARY_SYSTEM, json.dumps(intents, indent=0))
        job.task_summary = str(res.get("summary", "")).strip()

        job.doc = {
            "video": job.video_path,
            "duration": round(job.duration, 3),
            "params": {"chunk_s": job.chunk_s, "language": job.language},
            "providers": {"asr": transcriber.info(), "llm": llm.info()},
            "task_summary": job.task_summary,
            "n_transcript_segments": len(segs),
            "n_intents": len(intents),
            "transcript": [s.as_dict() for s in segs],
            "intents": intents,
        }
        job.intents = intents
        job.progress = 1.0
        job.state = "done"
    except Exception as e:  # noqa: BLE001
        job.state = "error"
        job.error = str(e)


def start(job: AudioJob) -> threading.Thread:
    t = threading.Thread(target=run, args=(job,), daemon=True)
    t.start()
    return t
