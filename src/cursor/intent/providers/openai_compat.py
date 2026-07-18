"""OpenAI-compatible providers.

Because these speak the plain OpenAI HTTP protocol with a configurable
base URL, they also cover Groq, OpenRouter, Azure-style gateways, local
vLLM / faster-whisper servers, etc. — switch via ASR_BASE_URL / LLM_BASE_URL.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from . import config
from .base import IntentModel, Transcriber, TranscriptSegment


class ApiError(RuntimeError):
    pass


def _raise_readable(resp: requests.Response, what: str):
    try:
        err = resp.json().get("error", {})
        msg = err.get("message", resp.text[:300])
        code = err.get("code", resp.status_code)
    except Exception:  # noqa: BLE001
        msg, code = resp.text[:300], resp.status_code
    raise ApiError(f"{what} failed ({code}): {msg}")


def _auth_check(base_url: str, key: str | None) -> dict:
    if not key:
        return {"ok": False, "detail": "no api key configured (set OPENAI_KEY in .env)"}
    try:
        r = requests.get(f"{base_url}/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=20)
    except requests.RequestException as e:
        return {"ok": False, "detail": f"cannot reach {base_url}: {e}"}
    if r.status_code != 200:
        return {"ok": False, "detail": f"auth failed (HTTP {r.status_code})"}
    return {"ok": True, "detail": "auth ok"}


class OpenAICompatTranscriber(Transcriber):
    name = "openai"

    def __init__(self):
        self.model = config.get("ASR_MODEL")
        self.base_url = config.get("ASR_BASE_URL").rstrip("/")
        self.key = config.api_key()

    def transcribe(self, wav_path: str, language: str | None = None):
        data = {"model": self.model, "response_format": "verbose_json"}
        if language:
            data["language"] = language
        with open(wav_path, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.key}"},
                data=data,
                files={"file": (Path(wav_path).name, f, "audio/wav")},
                timeout=600,
            )
        if resp.status_code != 200:
            _raise_readable(resp, "transcription")
        doc = resp.json()
        segs = doc.get("segments") or []
        out = [TranscriptSegment(float(s["start"]), float(s["end"]), s["text"].strip())
               for s in segs if s.get("text", "").strip()]
        if not out and doc.get("text", "").strip():
            # provider returned plain text without segments; one big segment
            out = [TranscriptSegment(0.0, float(doc.get("duration", 0.0)), doc["text"].strip())]
        return out

    def check(self):
        return _auth_check(self.base_url, self.key)


class OpenAICompatChat(IntentModel):
    name = "openai"

    def __init__(self):
        self.model = config.get("LLM_MODEL")
        self.base_url = config.get("LLM_BASE_URL").rstrip("/")
        self.key = config.api_key()

    def _call(self, messages: list[dict]) -> str:
        # OpenAI default temperature is 1.0. Low values (e.g. 0.2) over-collapse
        # sampling; some models (gpt-5.6-luna) only accept the default.
        temp_raw = config.get("LLM_TEMPERATURE", "1")
        try:
            temperature = float(temp_raw) if temp_raw not in (None, "") else 1.0
        except ValueError:
            temperature = 1.0
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=300,
        )
        if resp.status_code != 200:
            _raise_readable(resp, "chat completion")
        return resp.json()["choices"][0]["message"]["content"]

    def complete_json(self, system: str, user: str) -> dict:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        raw = self._call(messages)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # one retry with the parse error fed back
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": "That was not valid JSON. Reply with ONLY the valid JSON object."})
            return json.loads(self._call(messages))

    def check(self):
        auth = _auth_check(self.base_url, self.key)
        if not auth["ok"]:
            return auth
        # 1-token end-to-end ping — also catches quota/billing problems
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.key}",
                         "Content-Type": "application/json"},
                json={"model": self.model,
                      "messages": [{"role": "user", "content": "ping"}],
                      "max_tokens": 1},
                timeout=30,
            )
            if resp.status_code != 200:
                _raise_readable(resp, "ping")
        except ApiError as e:
            return {"ok": False, "detail": str(e)}
        except requests.RequestException as e:
            return {"ok": False, "detail": str(e)}
        return {"ok": True, "detail": "auth + completion ok"}
