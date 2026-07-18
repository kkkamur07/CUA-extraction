import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

import type { IntentJob } from "@/components/workbench/types";
import { getIntentProviderStatus } from "@/lib/intentConfig";
import {
  actionIntentPairsPath,
  intentJobPath,
  speechFullPath,
  speechTrimmedPath,
  summaryPath,
} from "@/lib/paths";
import {
  isValidProjectId,
  requireSelection,
  runDirRelative,
  spawnCursorDetached,
} from "@/lib/python";

export const runtime = "nodejs";
export const maxDuration = 60;

async function readJson(filePath: string): Promise<unknown | null> {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

async function loadIntentArtifacts(id: string) {
  const [speechFull, speechTrimmed, summaryDoc, pairsDoc] = await Promise.all([
    readJson(speechFullPath(id)),
    readJson(speechTrimmedPath(id)),
    readJson(summaryPath(id)),
    readJson(actionIntentPairsPath(id)),
  ]);

  const summary =
    summaryDoc && typeof summaryDoc === "object" && summaryDoc !== null && "summary" in summaryDoc
      ? String((summaryDoc as { summary: unknown }).summary ?? "")
      : null;

  let pairs: unknown[] = [];
  if (Array.isArray(pairsDoc)) {
    pairs = pairsDoc;
  } else if (
    pairsDoc &&
    typeof pairsDoc === "object" &&
    "action_intent_pairs" in pairsDoc &&
    Array.isArray((pairsDoc as { action_intent_pairs: unknown }).action_intent_pairs)
  ) {
    pairs = (pairsDoc as { action_intent_pairs: unknown[] }).action_intent_pairs;
  } else if (
    pairsDoc &&
    typeof pairsDoc === "object" &&
    "pairs" in pairsDoc &&
    Array.isArray((pairsDoc as { pairs: unknown }).pairs)
  ) {
    pairs = (pairsDoc as { pairs: unknown[] }).pairs;
  }

  return { speechFull, speechTrimmed, summary, pairs };
}

const ACTIVE = new Set(["starting", "running", "extracting", "transcribing", "summarizing"]);

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!isValidProjectId(id)) {
    return NextResponse.json({ error: "Invalid project id" }, { status: 400 });
  }

  const [artifacts, providers, jobRaw] = await Promise.all([
    loadIntentArtifacts(id),
    getIntentProviderStatus(),
    readJson(intentJobPath(id)),
  ]);
  const job = (jobRaw as IntentJob | null) ?? null;
  const ready = Boolean(artifacts.speechFull || artifacts.speechTrimmed);
  return NextResponse.json({
    ok: ready,
    run_id: id,
    providers,
    job,
    ...artifacts,
  });
}

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!isValidProjectId(id)) {
    return NextResponse.json({ error: "Invalid project id" }, { status: 400 });
  }

  try {
    await requireSelection(id);
  } catch {
    return NextResponse.json(
      { error: "Save a selection before running intent extraction" },
      { status: 400 },
    );
  }

  const existing = (await readJson(intentJobPath(id))) as IntentJob | null;
  if (existing?.state && ACTIVE.has(existing.state)) {
    return NextResponse.json({
      ok: true,
      run_id: id,
      started: false,
      already_running: true,
      job: existing,
    });
  }

  await fs.mkdir(path.dirname(intentJobPath(id)), { recursive: true });
  await fs.writeFile(
    intentJobPath(id),
    JSON.stringify(
      {
        state: "starting",
        progress: 0,
        error: null,
        message: "Starting intent job…",
        n_segments: 0,
        n_intents: 0,
        updated_at: Date.now() / 1000,
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );

  const { pid } = spawnCursorDetached([
    "extract-intent-async",
    runDirRelative(id),
    "--json",
  ]);

  return NextResponse.json({
    ok: true,
    run_id: id,
    started: true,
    pid: pid ?? null,
    message: "Intent extraction started",
  });
}
