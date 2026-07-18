import { promises as fs } from "node:fs";
import path from "node:path";

import type { IntentProviderStatus } from "@/components/workbench/types";
import { REPO_ROOT } from "@/lib/paths";

export type { IntentProviderStatus };

const DEFAULTS = {
  ASR_PROVIDER: "openai",
  ASR_MODEL: "whisper-1",
  LLM_PROVIDER: "openai",
  LLM_MODEL: "gpt-4o-mini",
} as const;

async function loadDotEnv(): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  try {
    const text = await fs.readFile(path.join(REPO_ROOT, ".env"), "utf8");
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const eq = trimmed.indexOf("=");
      const key = trimmed.slice(0, eq).trim();
      let value = trimmed.slice(eq + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      if (key) out[key] = value;
    }
  } catch {
    /* no .env */
  }
  return out;
}

function pick(
  env: Record<string, string>,
  keys: string[],
  fallback = "",
): string {
  for (const key of keys) {
    const fromProcess = process.env[key]?.trim();
    if (fromProcess) return fromProcess;
    const fromFile = env[key]?.trim();
    if (fromFile) return fromFile;
  }
  return fallback;
}

/** Read ASR/LLM connection status from env + repo `.env` (never returns secrets). */
export async function getIntentProviderStatus(): Promise<IntentProviderStatus> {
  const fileEnv = await loadDotEnv();
  const apiKey = pick(fileEnv, ["OPENAI_API_KEY", "OPENAI_KEY", "CURSOR_LLM_API_KEY"]);
  const apiKeyConnected = apiKey.length > 0;

  const asrProvider = DEFAULTS.ASR_PROVIDER;
  const asrModel = pick(
    fileEnv,
    ["ASR_MODEL", "CURSOR_ASR_MODEL"],
    DEFAULTS.ASR_MODEL,
  );
  const llmProvider = DEFAULTS.LLM_PROVIDER;
  const llmModel = pick(
    fileEnv,
    ["LLM_MODEL", "CURSOR_LLM_MODEL"],
    DEFAULTS.LLM_MODEL,
  );

  return {
    apiKeyConnected,
    asrProvider,
    asrModel,
    asrReady: apiKeyConnected && Boolean(asrModel),
    llmProvider,
    llmModel,
    llmReady: apiKeyConnected && Boolean(llmModel),
  };
}
