import { promises as fs } from "node:fs";
import path from "node:path";

import {
  cursorFilterConfigPath,
  cursorFilterSummaryPath,
} from "@/lib/paths";
import {
  DEFAULT_CURSOR_FILTER,
  type CursorFilterCriteria,
} from "@/lib/types";

export function normalizeCursorFilter(
  raw: unknown,
): CursorFilterCriteria {
  const source =
    raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const nested =
    source.filter && typeof source.filter === "object"
      ? (source.filter as Record<string, unknown>)
      : source;

  const minConfidence = Number(
    nested.min_confidence ?? DEFAULT_CURSOR_FILTER.min_confidence,
  );
  const minMovePx = Number(
    nested.min_move_px ?? DEFAULT_CURSOR_FILTER.min_move_px,
  );

  return {
    min_confidence: Number.isFinite(minConfidence)
      ? Math.min(1, Math.max(0, minConfidence))
      : DEFAULT_CURSOR_FILTER.min_confidence,
    min_move_px: Number.isFinite(minMovePx)
      ? Math.max(0, minMovePx)
      : DEFAULT_CURSOR_FILTER.min_move_px,
  };
}

export async function loadCursorFilter(
  id: string,
): Promise<CursorFilterCriteria> {
  for (const filePath of [
    cursorFilterConfigPath(id),
    cursorFilterSummaryPath(id),
  ]) {
    try {
      const text = await fs.readFile(filePath, "utf8");
      return normalizeCursorFilter(JSON.parse(text));
    } catch {
      // try next
    }
  }
  return { ...DEFAULT_CURSOR_FILTER };
}

export async function saveCursorFilter(
  id: string,
  filter: CursorFilterCriteria,
): Promise<void> {
  const filePath = cursorFilterConfigPath(id);
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(
    filePath,
    JSON.stringify(normalizeCursorFilter(filter), null, 2) + "\n",
    "utf8",
  );
}

export function cursorFilterArgs(filter: CursorFilterCriteria): string[] {
  const normalized = normalizeCursorFilter(filter);
  return [
    "--min-confidence",
    String(normalized.min_confidence),
    "--min-move-px",
    String(normalized.min_move_px),
  ];
}
