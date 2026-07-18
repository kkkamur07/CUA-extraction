import { createReadStream, promises as fs, statSync } from "node:fs";
import { Readable } from "node:stream";
import { NextRequest, NextResponse } from "next/server";

import { videoFilePath } from "@/lib/paths";

export const runtime = "nodejs";

/** Default slice when the client sends an open-ended Range (bytes=N-). */
const DEFAULT_CHUNK = 4 * 1024 * 1024;

function contentType(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".webm")) return "video/webm";
  if (lower.endsWith(".mov")) return "video/quicktime";
  if (lower.endsWith(".mkv")) return "video/x-matroska";
  return "video/mp4";
}

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

  const stat = statSync(filePath);
  const range = request.headers.get("range");
  const type = contentType(decoded);
  const commonHeaders = {
    "Content-Type": type,
    "Accept-Ranges": "bytes",
    "Cache-Control": "public, max-age=3600",
  };

  if (range) {
    const match = /bytes=(\d+)-(\d*)/.exec(range);
    if (!match) {
      return NextResponse.json({ error: "Invalid range" }, { status: 416 });
    }
    const start = Number(match[1]);
    const end = match[2]
      ? Math.min(Number(match[2]), stat.size - 1)
      : Math.min(start + DEFAULT_CHUNK - 1, stat.size - 1);

    if (start >= stat.size || start > end) {
      return new NextResponse(null, {
        status: 416,
        headers: { "Content-Range": `bytes */${stat.size}` },
      });
    }

    const stream = createReadStream(filePath, { start, end });
    return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
      status: 206,
      headers: {
        ...commonHeaders,
        "Content-Length": String(end - start + 1),
        "Content-Range": `bytes ${start}-${end}/${stat.size}`,
      },
    });
  }

  const stream = createReadStream(filePath);
  return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
    headers: {
      ...commonHeaders,
      "Content-Length": String(stat.size),
    },
  });
}
