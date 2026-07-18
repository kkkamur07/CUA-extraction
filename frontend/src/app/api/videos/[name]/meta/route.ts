import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import { promisify } from "node:util";
import { NextResponse } from "next/server";

import { videoFilePath } from "@/lib/paths";

export const runtime = "nodejs";

const execFileAsync = promisify(execFile);

export async function GET(
  _request: Request,
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

  try {
    const { stdout } = await execFileAsync(
      "ffprobe",
      [
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate:format=duration",
        "-of",
        "json",
        filePath,
      ],
      { timeout: 30_000 },
    );
    const parsed = JSON.parse(stdout) as {
      streams?: Array<{ width?: number; height?: number; r_frame_rate?: string }>;
      format?: { duration?: string };
    };
    const stream = parsed.streams?.[0];
    const width = Number(stream?.width) || 1920;
    const height = Number(stream?.height) || 1080;
    const duration = Number(parsed.format?.duration) || 0;
    let fps = 30;
    const rate = stream?.r_frame_rate;
    if (rate && rate.includes("/")) {
      const [num, den] = rate.split("/").map(Number);
      if (num > 0 && den > 0) fps = num / den;
    }
    return NextResponse.json({ width, height, duration, fps });
  } catch (err) {
    return NextResponse.json(
      {
        error:
          err instanceof Error
            ? err.message
            : "Failed to probe video metadata (is ffprobe installed?)",
      },
      { status: 500 },
    );
  }
}
