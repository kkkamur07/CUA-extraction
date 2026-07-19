import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

import {
  VIDEO_DIR,
  finalVideoPath,
  selectionPath,
  slugFromVideoName,
} from "@/lib/paths";
import type { VideoInfo } from "@/lib/types";

export const runtime = "nodejs";

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

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
    const [hasSelection, hasFinalOutput] = await Promise.all([
      pathExists(selectionPath(id)),
      pathExists(finalVideoPath(id)),
    ]);
    videos.push({
      name,
      id,
      path: `video/${name}`,
      sizeBytes: stat.size,
      hasSelection,
      hasFinalOutput,
    });
  }

  return NextResponse.json({ videos });
}
