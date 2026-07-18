import { promises as fs } from "node:fs";
import { NextRequest, NextResponse } from "next/server";

import { dataProjectDir, projectDir, selectionPath } from "@/lib/paths";
import path from "node:path";
import {
  flattenScreen,
  type ProjectSelection,
  type TrackSelection,
} from "@/lib/types";

export const runtime = "nodejs";

function isRoi(value: unknown): value is TrackSelection["roi"] {
  if (!value || typeof value !== "object") return false;
  const roi = value as Record<string, unknown>;
  return (
    typeof roi.x === "number" &&
    typeof roi.y === "number" &&
    typeof roi.width === "number" &&
    typeof roi.height === "number"
  );
}

function isTrack(value: unknown): value is TrackSelection {
  if (!value || typeof value !== "object") return false;
  const track = value as Record<string, unknown>;
  return (
    isRoi(track.roi) &&
    typeof track.start === "number" &&
    typeof track.end === "number" &&
    typeof track.preview_timestamp === "number"
  );
}

function normalize(raw: Record<string, unknown>, id: string): ProjectSelection | null {
  if (typeof raw.video !== "string") return null;
  if (typeof raw.fps !== "number") return null;
  if (typeof raw.frame_width !== "number" || typeof raw.frame_height !== "number") {
    return null;
  }

  let screen: TrackSelection | null = null;
  let keyboard: TrackSelection | null = null;

  if (isTrack(raw.screen)) screen = raw.screen;
  if (isTrack(raw.keyboard)) keyboard = raw.keyboard;

  if (!screen && isRoi(raw.roi) && typeof raw.start === "number" && typeof raw.end === "number") {
    screen = {
      roi: raw.roi,
      start: raw.start,
      end: raw.end,
      preview_timestamp:
        typeof raw.preview_timestamp === "number" ? raw.preview_timestamp : raw.start,
    };
  }

  if (!screen) return null;
  if (!keyboard) {
    keyboard = {
      roi: { x: 0, y: 0, width: raw.frame_width, height: Math.min(240, raw.frame_height) },
      start: screen.start,
      end: screen.end,
      preview_timestamp: screen.preview_timestamp,
    };
  }

  return flattenScreen({
    id,
    video: raw.video,
    fps: raw.fps,
    frame_width: raw.frame_width,
    frame_height: raw.frame_height,
    preview_timestamp: screen.preview_timestamp,
    roi: screen.roi,
    start: screen.start,
    end: screen.end,
    screen,
    keyboard,
  });
}

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  try {
    const text = await fs.readFile(selectionPath(id), "utf8");
    const normalized = normalize(JSON.parse(text) as Record<string, unknown>, id);
    if (!normalized) {
      return NextResponse.json({ error: "Invalid selection.json" }, { status: 500 });
    }
    return NextResponse.json(normalized);
  } catch {
    return NextResponse.json({ selection: null });
  }
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const body = (await request.json()) as Record<string, unknown>;
  const normalized = normalize({ ...body, id }, id);
  if (!normalized) {
    return NextResponse.json({ error: "Invalid selection payload" }, { status: 400 });
  }
  if (normalized.end <= normalized.start || normalized.screen.end <= normalized.screen.start) {
    return NextResponse.json(
      { error: "Screen end time must be greater than start time" },
      { status: 400 },
    );
  }
  if (normalized.keyboard.end <= normalized.keyboard.start) {
    return NextResponse.json(
      { error: "Keyboard end time must be greater than start time" },
      { status: 400 },
    );
  }

  const dir = projectDir(id);
  await fs.mkdir(dir, { recursive: true });
  const payload = flattenScreen(normalized);
  const text = JSON.stringify(payload, null, 2);
  await fs.writeFile(selectionPath(id), text, "utf8");
  // Keep a training-data copy under data/<id>/ for YOLO scripts.
  const dataDir = dataProjectDir(id);
  await fs.mkdir(dataDir, { recursive: true });
  await fs.writeFile(path.join(dataDir, "selection.json"), text, "utf8");
  return NextResponse.json(payload);
}
