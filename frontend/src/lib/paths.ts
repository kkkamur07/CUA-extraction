import path from "node:path";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
export const VIDEO_DIR = path.join(REPO_ROOT, "video");
export const RUNS_DIR = path.join(REPO_ROOT, "runs");
export const DATA_DIR = path.join(REPO_ROOT, "data");
export const ARTIFACTS_DIR = path.join(REPO_ROOT, "artifacts");

export function projectDir(id: string): string {
  return path.join(RUNS_DIR, id);
}

export function dataProjectDir(id: string): string {
  return path.join(DATA_DIR, id);
}

/** Published final dataset directory; traces and jobs stay under runs/<id>. */
export function publishedProjectDir(id: string): string {
  return dataProjectDir(id);
}

export function publishedSelectionPath(id: string): string {
  return path.join(publishedProjectDir(id), "selection.json");
}

export function selectionPath(id: string): string {
  return path.join(projectDir(id), "selection.json");
}

export function keystrokesPath(id: string): string {
  return path.join(projectDir(id), "trace", "keystrokes", "keystrokes.json");
}

export function finalKeystrokesPath(id: string): string {
  return path.join(publishedProjectDir(id), "keystrokes", "final_keystrokes.json");
}

export function rawKeystrokesPath(id: string): string {
  return path.join(projectDir(id), "keystrokes", "raw_keystrokes.json");
}

export function publishedRawKeystrokesPath(id: string): string {
  return path.join(publishedProjectDir(id), "keystrokes", "raw_keystrokes.json");
}

export function keystrokeJobPath(id: string): string {
  return path.join(projectDir(id), "trace", "keystrokes", "keystroke_job.json");
}

export function cursorEventsPath(id: string): string {
  return path.join(projectDir(id), "trace", "cursor", "cursor_events.jsonl");
}

export function finalCursorEventsPath(id: string): string {
  return path.join(publishedProjectDir(id), "cursor", "final_cursor_events.jsonl");
}

export function rawCursorEventsPath(id: string): string {
  return path.join(projectDir(id), "cursor", "raw_cursor_events.jsonl");
}

export function publishedRawCursorEventsPath(id: string): string {
  return path.join(publishedProjectDir(id), "cursor", "raw_cursor_events.jsonl");
}

export function cursorFilterSummaryPath(id: string): string {
  return path.join(projectDir(id), "trace", "cursor", "filter_summary.json");
}

export function cursorFilterConfigPath(id: string): string {
  return path.join(projectDir(id), "trace", "cursor", "filter_config.json");
}

export function mouseEventsPath(id: string): string {
  return path.join(projectDir(id), "trace", "cursor", "mouse_events.jsonl");
}

export function finalMouseEventsPath(id: string): string {
  return path.join(publishedProjectDir(id), "cursor", "final_mouse_events.jsonl");
}

export function finalProcessingSummaryPath(id: string): string {
  return path.join(publishedProjectDir(id), "trace", "final_processing_summary.json");
}

export function speechFullPath(id: string): string {
  return path.join(projectDir(id), "trace", "intent", "speech_full.json");
}

export function finalSpeechFullPath(id: string): string {
  return path.join(publishedProjectDir(id), "intent", "final_speech_full.json");
}

export function speechTrimmedPath(id: string): string {
  return path.join(projectDir(id), "trace", "intent", "speech_trimmed.json");
}

export function finalSpeechTrimmedPath(id: string): string {
  return path.join(publishedProjectDir(id), "intent", "final_speech_trimmed.json");
}

export function intentJobPath(id: string): string {
  return path.join(projectDir(id), "trace", "intent", "intent_job.json");
}

export function summaryPath(id: string): string {
  return path.join(projectDir(id), "trace", "summary", "summary.json");
}

export function finalSummaryPath(id: string): string {
  return path.join(publishedProjectDir(id), "summary", "final_summary.json");
}

export function actionIntentPairsPath(id: string): string {
  return path.join(projectDir(id), "trace", "intent", "action_intent_pairs.json");
}

export function finalActionIntentPairsPath(id: string): string {
  return path.join(publishedProjectDir(id), "intent", "final_action_intent_pairs.json");
}

export function workflowSamplePath(id: string): string {
  return path.join(projectDir(id), "trace", "workflow_sample.json");
}

export function finalWorkflowSamplePath(id: string): string {
  return path.join(publishedProjectDir(id), "final_workflow_sample.json");
}

export function finalVideoPath(id: string): string {
  return path.join(publishedProjectDir(id), "final_video.mp4");
}

export function finalVideoManifestPath(id: string): string {
  return path.join(publishedProjectDir(id), "final_video.json");
}

export function metadataPath(id: string): string {
  return path.join(publishedProjectDir(id), "metadata.json");
}

/** Cursor annotation patches + manifest used for YOLO training. */
export function templatesDir(id: string): string {
  return path.join(dataProjectDir(id), "templates");
}

export function predictionsDir(id: string): string {
  return path.join(ARTIFACTS_DIR, "predictions", id);
}

export function videoFilePath(name: string): string {
  return path.join(VIDEO_DIR, name);
}

export function slugFromVideoName(name: string): string {
  return path.parse(name).name;
}
