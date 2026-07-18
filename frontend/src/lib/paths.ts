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

export function selectionPath(id: string): string {
  return path.join(projectDir(id), "selection.json");
}

export function keystrokesPath(id: string): string {
  return path.join(projectDir(id), "keystrokes", "keystrokes.json");
}

export function keystrokeJobPath(id: string): string {
  return path.join(projectDir(id), "keystrokes", "keystroke_job.json");
}

export function cursorEventsPath(id: string): string {
  return path.join(projectDir(id), "cursor", "cursor_events.jsonl");
}

export function speechFullPath(id: string): string {
  return path.join(projectDir(id), "intent", "speech_full.json");
}

export function speechTrimmedPath(id: string): string {
  return path.join(projectDir(id), "intent", "speech_trimmed.json");
}

export function intentJobPath(id: string): string {
  return path.join(projectDir(id), "intent", "intent_job.json");
}

export function summaryPath(id: string): string {
  return path.join(projectDir(id), "summary", "summary.json");
}

export function actionIntentPairsPath(id: string): string {
  return path.join(projectDir(id), "intent", "action_intent_pairs.json");
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
