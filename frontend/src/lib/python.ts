import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";

import { REPO_ROOT, selectionPath } from "@/lib/paths";

const PYTHON = path.join(REPO_ROOT, ".venv", "bin", "python");

export function isValidProjectId(id: string): boolean {
  return Boolean(id) && !id.includes("..") && !id.includes("/") && !id.includes("\\");
}

export async function requireSelection(id: string): Promise<void> {
  await fs.access(selectionPath(id));
}

/** Run a short-lived `python -m cursor …` command; collect stdout/stderr. */
export function runCursor(
  args: string[],
): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(PYTHON, ["-m", "cursor", ...args], {
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
        stderr: `${stderr}\nFailed to spawn python: ${err.message}`.trim(),
      });
    });
    child.on("close", (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

/** Run an in-repository Python script and collect stdout/stderr. */
export function runPythonScript(
  script: string,
  args: string[],
): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(PYTHON, [script, ...args], {
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
        stderr: `${stderr}\nFailed to spawn Python script: ${err.message}`.trim(),
      });
    });
    child.on("close", (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

/** Run a `python -m cursor …` command that writes binary data to stdout. */
export function runCursorBinary(
  args: string[],
): Promise<{ code: number | null; stdout: Buffer; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(PYTHON, ["-m", "cursor", ...args], {
      cwd: REPO_ROOT,
      env: process.env,
    });
    const chunks: Buffer[] = [];
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      chunks.push(chunk);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (err) => {
      resolve({
        code: 1,
        stdout: Buffer.concat(chunks),
        stderr: `${stderr}\nFailed to spawn python: ${err.message}`.trim(),
      });
    });
    child.on("close", (code) => {
      resolve({ code, stdout: Buffer.concat(chunks), stderr });
    });
  });
}

/** Start a long-lived cursor CLI subprocess detached from the request. */
export function spawnCursorDetached(args: string[]): { pid: number | undefined } {
  const child = spawn(PYTHON, ["-m", "cursor", ...args], {
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
