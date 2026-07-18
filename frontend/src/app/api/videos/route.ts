import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

import {
  VIDEO_DIR,
  selectionPath,
  slugFromVideoName,
} from "@/lib/paths";
import type { VideoInfo } from "@/lib/types";

export const runtime = "nodejs";

export async function GET() {
  await fs.mkdir(VIDEO_DIR, { recursive: true });
  const entries = await fs.readdir(VIDEO_DIR);
  const videos: VideoInfo[] = [];

  for (const name of entries.sort()) {
    if (!/\.(mp4|mov|webm|mkv)$/i.test(name)) continue;
    const filePath = path.join(VIDEO_DIR, name);
    const stat = await fs.stat(filePath);
    if (!stat.isFile()) continue;
    const id = slugFromVideoName(name);
    let hasSelection = false;
    try {
      await fs.access(selectionPath(id));
      hasSelection = true;
    } catch {
      hasSelection = false;
    }
    videos.push({
      name,
      id,
      path: `video/${name}`,
      sizeBytes: stat.size,
      hasSelection,
    });
  }

  return NextResponse.json({ videos });
}
