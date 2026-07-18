import { promises as fs } from "node:fs";
import path from "node:path";

import { REPO_ROOT } from "@/lib/paths";

/** Mirrors ``cursor.detector.cursor_events.DEFAULT_MODEL_PATH``. */
export const DEFAULT_CURSOR_WEIGHTS = "artifacts/models/cursor/weights/best.pt";

export type CursorWeightsStatus = {
  found: boolean;
  path: string;
};

/** Check whether default YOLO cursor weights exist on disk. */
export async function getCursorWeightsStatus(): Promise<CursorWeightsStatus> {
  const rel = DEFAULT_CURSOR_WEIGHTS;
  const abs = path.join(REPO_ROOT, rel);
  try {
    await fs.access(abs);
    return { found: true, path: rel };
  } catch {
    return { found: false, path: rel };
  }
}
