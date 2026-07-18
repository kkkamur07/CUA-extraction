export type Tab = "screen" | "keyboard" | "intent" | "cursor";
export type CursorMode = "labels" | "extract";

export type IntentProviderStatus = {
  apiKeyConnected: boolean;
  asrProvider: string;
  asrModel: string;
  asrReady: boolean;
  llmProvider: string;
  llmModel: string;
  llmReady: boolean;
};

export type IntentJob = {
  state?: string;
  progress?: number;
  error?: string | null;
  message?: string;
  n_segments?: number;
  n_intents?: number;
};

export type CursorWeightsStatus = {
  found: boolean;
  path: string;
};

export type KeystrokeJob = {
  state?: string;
  progress?: number;
  error?: string | null;
  n_samples?: number;
  n_events?: number;
  message?: string;
};

export const LABEL_PRESETS = [
  "arrow_white",
  "pencil",
  "crosshair_black",
  "hand",
] as const;

export const WORKBENCH_TABS: { id: Tab; label: string }[] = [
  { id: "screen", label: "Screen extraction" },
  { id: "keyboard", label: "Keyboard extraction" },
  { id: "intent", label: "Intent extraction" },
  { id: "cursor", label: "Cursor" },
];
