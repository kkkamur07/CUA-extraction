import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

import {
  cursorFilterArgs,
  loadCursorFilter,
  normalizeCursorFilter,
  saveCursorFilter,
} from "@/lib/cursorFilter";
import {
  actionIntentPairsPath,
  cursorEventsPath,
  finalProcessingSummaryPath,
  finalVideoManifestPath,
  finalVideoPath,
  metadataPath,
  keystrokesPath,
  mouseEventsPath,
  publishedProjectDir,
  publishedRawCursorEventsPath,
  publishedRawKeystrokesPath,
  publishedSelectionPath,
  rawCursorEventsPath,
  rawKeystrokesPath,
  selectionPath,
  speechFullPath,
  speechTrimmedPath,
  summaryPath as summaryArtifactPath,
} from "@/lib/paths";
import {
  isValidProjectId,
  requireSelection,
  runPythonScript,
  runDirRelative,
} from "@/lib/python";

export const runtime = "nodejs";
export const maxDuration = 1800;

async function countJsonl(filePath: string): Promise<number> {
  try {
    const text = await fs.readFile(filePath, "utf8");
    return text.split("\n").filter((line) => line.trim()).length;
  } catch {
    return 0;
  }
}

async function countJsonEvents(filePath: string): Promise<number> {
  try {
    const payload = JSON.parse(await fs.readFile(filePath, "utf8")) as {
      events?: unknown;
    };
    return Array.isArray(payload.events) ? payload.events.length : 0;
  } catch {
    return 0;
  }
}

async function copyArtifact(sourcePath: string, outputPath: string): Promise<void> {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.copyFile(sourcePath, outputPath);
}

async function requireArtifacts(
  id: string,
  artifacts: Array<[string, string]>,
): Promise<string | null> {
  for (const [label, filePath] of artifacts) {
    try {
      await fs.access(filePath);
    } catch {
      return `Run ${label} first; missing ${path.relative(process.cwd(), filePath)}`;
    }
  }
  return null;
}

async function fail(
  id: string,
  step: string,
  result: { code: number | null; stdout: string; stderr: string },
) {
  return NextResponse.json(
    {
      ok: false,
      run_id: id,
      step,
      error:
        result.stderr.trim() ||
        result.stdout.trim() ||
        `${step} exited with code ${result.code}`,
    },
    { status: 500 },
  );
}

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!isValidProjectId(id)) {
    return NextResponse.json({ error: "Invalid project id" }, { status: 400 });
  }

  try {
    await requireSelection(id);
  } catch {
    return NextResponse.json(
      { error: "Save a selection before processing events" },
      { status: 400 },
    );
  }

  let body: Record<string, unknown> = {};
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }

  const savedFilter = await loadCursorFilter(id);
  const filter = normalizeCursorFilter({ ...savedFilter, ...body });
  await saveCursorFilter(id, filter);

  const runDir = runDirRelative(id);
  const rawCursorRelative = path.join(runDir, "cursor", "raw_cursor_events.jsonl");
  const filteredCursorRelative = path.join(
    runDir,
    "trace",
    "cursor",
    "cursor_events.jsonl",
  );
  const rawKeyboardRelative = path.join(runDir, "keystrokes", "raw_keystrokes.json");
  const filteredKeyboardRelative = path.join(
    runDir,
    "trace",
    "keystrokes",
    "keystrokes.json",
  );
  const requiredError = await requireArtifacts(id, [
    ["cursor extraction", rawCursorEventsPath(id)],
    ["keyboard extraction", rawKeystrokesPath(id)],
    ["intent extraction", speechFullPath(id)],
    ["intent extraction", speechTrimmedPath(id)],
    ["intent extraction", summaryArtifactPath(id)],
    ["intent extraction", actionIntentPairsPath(id)],
  ]);
  if (requiredError) {
    return NextResponse.json({ ok: false, run_id: id, error: requiredError }, { status: 400 });
  }

  const cursorFiltering = await runPythonScript("scripts/filter_cursor_events.py", [
    "--input",
    rawCursorRelative,
    "--output",
    filteredCursorRelative,
    ...cursorFilterArgs(filter),
  ]);
  if (cursorFiltering.code !== 0) {
    return fail(id, "cursor filtering", cursorFiltering);
  }

  const keyboardFiltering = await runPythonScript("scripts/split_mouse_events.py", [
    runDir,
    "--input",
    rawKeyboardRelative,
    "--raw-output",
    rawKeyboardRelative,
    "--keyboard-output",
    filteredKeyboardRelative,
  ]);
  if (keyboardFiltering.code !== 0) {
    return fail(id, "keyboard event filtering", keyboardFiltering);
  }

  // Final artifacts are normalized onto the final-clip timeline: times are
  // shifted so the selection start becomes 0, and cursor coordinates become
  // screen-crop-relative to match the cropped final video.
  const normalization = await runPythonScript("scripts/normalize_final_events.py", [
    runDir,
    "--output-dir",
    publishedProjectDir(id),
  ]);
  if (normalization.code !== 0) {
    return fail(id, "final artifact normalization", normalization);
  }

  await Promise.all([
    copyArtifact(selectionPath(id), publishedSelectionPath(id)),
    copyArtifact(rawCursorEventsPath(id), publishedRawCursorEventsPath(id)),
    copyArtifact(rawKeystrokesPath(id), publishedRawKeystrokesPath(id)),
  ]);

  const finalVideoOutput = finalVideoPath(id);
  const finalVideoRender = await runPythonScript("scripts/render_final_video.py", [
    "--selection",
    path.join(runDir, "selection.json"),
    "--output",
    finalVideoOutput,
  ]);
  if (finalVideoRender.code !== 0) {
    return fail(id, "final video rendering", finalVideoRender);
  }

  const summaryPath = finalProcessingSummaryPath(id);
  const summary = {
    run_id: id,
    status: "complete",
    source: "existing extraction artifacts",
    cursor_filter: filter,
    artifacts: {
      final_cursor: path.join("data", id, "cursor", "final_cursor_events.jsonl"),
      final_mouse: path.join("data", id, "cursor", "final_mouse_events.jsonl"),
      final_keyboard: path.join("data", id, "keystrokes", "final_keystrokes.json"),
      final_speech_full: path.join("data", id, "intent", "final_speech_full.json"),
      final_speech_trimmed: path.join("data", id, "intent", "final_speech_trimmed.json"),
      final_action_intent_pairs: path.join(
        "data",
        id,
        "intent",
        "final_action_intent_pairs.json",
      ),
      final_summary: path.join("data", id, "summary", "final_summary.json"),
      final_video: path.join("data", id, "final_video.mp4"),
      final_video_manifest: path.join("data", id, "final_video.json"),
      final_processing_summary: path.join(
        "data",
        id,
        "trace",
        "final_processing_summary.json",
      ),
      metadata: path.join("data", id, "metadata.json"),
    },
    intermediate_artifacts: {
      raw_cursor: rawCursorRelative,
      filtered_cursor: filteredCursorRelative,
      raw_keyboard: rawKeyboardRelative,
      filtered_keyboard: filteredKeyboardRelative,
      mouse_buttons: path.join(runDir, "trace", "cursor", "mouse_events.jsonl"),
    },
    counts: {
      raw_cursor: await countJsonl(rawCursorEventsPath(id)),
      filtered_cursor: await countJsonl(cursorEventsPath(id)),
      mouse_buttons: await countJsonl(mouseEventsPath(id)),
      raw_keyboard: await countJsonEvents(rawKeystrokesPath(id)),
      filtered_keyboard: await countJsonEvents(keystrokesPath(id)),
    },
  };
  await fs.mkdir(path.dirname(summaryPath), { recursive: true });
  await fs.writeFile(summaryPath, JSON.stringify(summary, null, 2) + "\n", "utf8");
  await fs.writeFile(
    metadataPath(id),
    JSON.stringify(
      {
        id,
        selection: path.join("data", id, "selection.json"),
        artifacts: summary.artifacts,
        counts: summary.counts,
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );

  return NextResponse.json({
    ok: true,
    run_id: id,
    summary,
    message: "Final events and cropped video generated",
    video: finalVideoPath(id),
    videoManifest: finalVideoManifestPath(id),
  });
}
