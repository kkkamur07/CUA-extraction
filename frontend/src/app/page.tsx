import { promises as fs } from "node:fs";
import path from "node:path";
import Link from "next/link";

import { VIDEO_DIR, selectionPath, slugFromVideoName } from "@/lib/paths";
import type { VideoInfo } from "@/lib/types";
import { RefreshButton } from "@/components/RefreshButton";

export const dynamic = "force-dynamic";

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function listVideos(): Promise<VideoInfo[]> {
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
  return videos;
}

export default async function HomePage() {
  const videos = await listVideos();

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-12">
      <header>
        <p className="text-sm uppercase tracking-[0.18em] text-[var(--accent)]">
          Cursor predict
        </p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl tracking-tight">
          Video library
        </h1>
        <p className="mt-3 max-w-xl text-[var(--muted)]">
          Repeat the same workflow across tutorials: set screen and keyboard
          extraction ranges, then label cursors. Put MP4s in{" "}
          <code className="font-mono text-sm">video/</code>.
        </p>
      </header>

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-[var(--muted)]">{videos.length} video(s)</p>
        <RefreshButton />
      </div>

      <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
        {videos.map((video) => (
          <li key={video.id}>
            <Link
              href={`/projects/${encodeURIComponent(video.id)}?file=${encodeURIComponent(video.name)}`}
              className="flex items-center justify-between gap-4 py-4 transition-colors hover:bg-[var(--wash)]"
            >
              <div>
                <p className="font-medium">{video.name}</p>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  {formatBytes(video.sizeBytes)}
                  {video.hasSelection ? " · selection saved" : " · no selection yet"}
                </p>
              </div>
              <span className="text-sm text-[var(--accent)]">Open →</span>
            </Link>
          </li>
        ))}
        {videos.length === 0 && (
          <li className="py-8 text-sm text-[var(--muted)]">
            No videos found. Add files under <code className="font-mono">video/</code>.
          </li>
        )}
      </ul>
    </div>
  );
}
