import { promises as fs } from "node:fs";
import { NextRequest, NextResponse } from "next/server";

import { videoFilePath } from "@/lib/paths";
import { runCursorBinary } from "@/lib/python";

export const runtime = "nodejs";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ name: string }> },
) {
  const { name } = await context.params;
  const decoded = decodeURIComponent(name);
  if (decoded.includes("..") || decoded.includes("/") || decoded.includes("\\")) {
    return NextResponse.json({ error: "Invalid video name" }, { status: 400 });
  }

  const filePath = videoFilePath(decoded);
  try {
    await fs.access(filePath);
  } catch {
    return NextResponse.json({ error: "Video not found" }, { status: 404 });
  }

  // Prefer exact frame numbers. Frames are decoded through the same OpenCV
  // path used when saving annotations and exporting the YOLO dataset, so the
  // pixels shown for labeling match the pixels trained on exactly. A time
  // fallback (`t`) is kept for callers that don't know the frame number; it is
  // rounded to a frame with the video's own fps.
  const rawFrame = request.nextUrl.searchParams.get("frame");
  const rawT = request.nextUrl.searchParams.get("t");

  let seekArgs: string[];
  if (rawFrame !== null) {
    const frame = Number(rawFrame);
    if (!Number.isInteger(frame) || frame < 0) {
      return NextResponse.json({ error: "Invalid frame number" }, { status: 400 });
    }
    seekArgs = ["--frame", String(frame)];
  } else {
    const time = Number(rawT ?? "0");
    seekArgs = [
      "--time",
      String(Number.isFinite(time) && time > 0 ? time : 0),
    ];
  }

  const { code, stdout, stderr } = await runCursorBinary([
    "dump-frame",
    filePath,
    ...seekArgs,
  ]);
  if (code !== 0 || !stdout.length) {
    return NextResponse.json(
      { error: stderr.trim() || "Failed to decode frame" },
      { status: 500 },
    );
  }

  return new NextResponse(new Uint8Array(stdout), {
    headers: {
      "Content-Type": "image/jpeg",
      "Cache-Control": "private, max-age=120",
    },
  });
}
