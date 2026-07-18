import { promises as fs } from "node:fs";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

import { REPO_ROOT, selectionPath, templatesDir } from "@/lib/paths";
import type { AnnotationRecord, TrackKind } from "@/lib/types";

export const runtime = "nodejs";

function safeLabel(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "cursor";
}

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const manifest = path.join(templatesDir(id), "templates.jsonl");
  try {
    const text = await fs.readFile(manifest, "utf8");
    const lines = text.split("\n").filter((line) => line.trim());
    return NextResponse.json({ count: lines.length, records: lines.map((line) => JSON.parse(line)) });
  } catch {
    return NextResponse.json({ count: 0, records: [] });
  }
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const body = (await request.json()) as {
    label?: string;
    frame_number?: number;
    timestamp_seconds?: number;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    ambiguous?: boolean;
    track?: TrackKind;
    image_data_url?: string;
  };

  const label = (body.label ?? "arrow_white").trim() || "arrow_white";
  const frameNumber = Number(body.frame_number);
  const timestamp = Number(body.timestamp_seconds);
  const x = Math.round(Number(body.x));
  const y = Math.round(Number(body.y));
  const width = Math.round(Number(body.width));
  const height = Math.round(Number(body.height));
  const track: TrackKind = body.track === "keyboard" ? "keyboard" : "screen";
  const imageDataUrl = body.image_data_url;

  if (
    !Number.isFinite(frameNumber) ||
    !Number.isFinite(timestamp) ||
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    width < 2 ||
    height < 2 ||
    !imageDataUrl?.startsWith("data:image/")
  ) {
    return NextResponse.json({ error: "Invalid annotation payload" }, { status: 400 });
  }

  try {
    await fs.access(selectionPath(id));
  } catch {
    return NextResponse.json(
      { error: "Save a selection for this video before labeling" },
      { status: 400 },
    );
  }

  const match = /^data:image\/\w+;base64,(.+)$/.exec(imageDataUrl);
  if (!match) {
    return NextResponse.json({ error: "Expected a base64 image data URL" }, { status: 400 });
  }

  const dir = templatesDir(id);
  await fs.mkdir(dir, { recursive: true });
  const filename =
    `cursor-${safeLabel(label)}-frame-${String(frameNumber).padStart(8, "0")}` +
    `-x${x}-y${y}-w${width}-h${height}.png`;
  const absolutePath = path.join(dir, filename);
  await fs.writeFile(absolutePath, Buffer.from(match[1], "base64"));

  const relativePath = path.relative(REPO_ROOT, absolutePath);
  const record: AnnotationRecord = {
    label,
    frame_number: frameNumber,
    timestamp_seconds: timestamp,
    x,
    y,
    width,
    height,
    center_x: x + Math.floor(width / 2),
    center_y: y + Math.floor(height / 2),
    ambiguous: Boolean(body.ambiguous),
    path: relativePath.replaceAll("\\", "/"),
    track,
  };

  const manifest = path.join(dir, "templates.jsonl");
  await fs.appendFile(manifest, `${JSON.stringify(record)}\n`, "utf8");
  return NextResponse.json({ record, path: relativePath.replaceAll("\\", "/") });
}
