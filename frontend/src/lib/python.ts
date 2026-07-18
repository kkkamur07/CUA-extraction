import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";

import { REPO_ROOT, selectionPath } from "@/lib/paths";

export function isValidProjectId(id: string): boolean {
  return Boolean(id) && !id.includes("..") && !id.includes("/") && !id.includes("\\");
}

export async function requireSelection(id: string): Promise<void> {
  await fs.access(selectionPath(id));
}

/** Run a short-lived `uv run python -m cursor …` command; collect stdout/stderr. */
export function runUvCursor(
  args: string[],
): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn("uv", ["run", "python", "-m", "cursor", ...args], {
      cwd: REPO_ROOT,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (err) => {
      resolve({
        code: 1,
        stdout,
        stderr: `${stderr}\nFailed to spawn uv: ${err.message}`.trim(),
      });
    });
    child.on("close", (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

/**
 * Start a long-lived cursor CLI subprocess detached from the request.
 * Used for keystroke jobs that write progress to disk.
 */
export function spawnUvCursorDetached(args: string[]): { pid: number | undefined } {
  const child = spawn("uv", ["run", "python", "-m", "cursor", ...args], {
    cwd: REPO_ROOT,
    env: process.env,
    detached: true,
    stdio: "ignore",
  });
  child.unref();
  return { pid: child.pid };
}

export function runDirRelative(id: string): string {
  return path.join("runs", id);
}
