"use client";

import type { ActionIntentPair } from "@/lib/types";

import { formatTime } from "./format";
import type { IntentJob, IntentProviderStatus } from "./types";

type Props = {
  runDisabled: boolean;
  running: boolean;
  job: IntentJob | null;
  summary: string | null;
  pairs: ActionIntentPair[];
  transcript: string | null;
  errors: Record<string, string>;
  providers: IntentProviderStatus | null;
  onRun: () => void;
};

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${
        ok
          ? "border-emerald-300 bg-emerald-50 text-emerald-900"
          : "border-amber-300 bg-amber-50 text-amber-950"
      }`}
    >
      <span aria-hidden>{ok ? "●" : "○"}</span>
      {label}
    </span>
  );
}

export function IntentTab({
  runDisabled,
  running,
  job,
  summary,
  pairs,
  transcript,
  errors,
  providers,
  onRun,
}: Props) {
  const progress = Math.round((job?.progress ?? 0) * 100);
  const showProgress = running || Boolean(job);

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4 rounded border border-[var(--line)] bg-[var(--wash)] p-4">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
            Intent extraction
          </p>
          <p className="mt-1 text-sm text-[var(--ink)]">
            Run speech transcription and Action–Intent extraction here. The
            final button combines these saved intent files with keyboard and
            cursor events.
          </p>
          {providers && (
            <div className="mt-3 flex flex-wrap gap-2">
              <StatusPill
                ok={providers.apiKeyConnected}
                label={
                  providers.apiKeyConnected
                    ? "API key connected"
                    : "API key missing"
                }
              />
              <StatusPill
                ok={providers.asrReady}
                label={
                  providers.asrReady
                    ? `ASR · ${providers.asrProvider} · ${providers.asrModel}`
                    : `ASR not ready · ${providers.asrProvider || "unset"}`
                }
              />
              <StatusPill
                ok={providers.llmReady}
                label={
                  providers.llmReady
                    ? `LLM · ${providers.llmProvider} · ${providers.llmModel}`
                    : `LLM not ready · ${providers.llmModel || "no model"}`
                }
              />
            </div>
          )}
          {showProgress && (
            <div className="mt-4 max-w-md space-y-2">
              <div className="h-2 overflow-hidden rounded bg-[var(--line)]">
                <div
                  className="h-full bg-[var(--accent)] transition-[width] duration-300"
                  style={{ width: `${job?.state === "done" ? 100 : progress}%` }}
                />
              </div>
              <p className="text-xs text-[var(--muted)]">
                {job?.message ||
                  (running ? `Running… ${progress}%` : "")}
                {job?.n_segments ? ` · ${job.n_segments} segments` : ""}
                {job?.n_intents ? ` · ${job.n_intents} pairs` : ""}
              </p>
            </div>
          )}
        </div>
        <button
          type="button"
          disabled={runDisabled || running}
          onClick={onRun}
          className="rounded bg-[var(--ink)] px-4 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
        >
          {running ? "Running…" : "Run intent extraction"}
        </button>
      </div>

      {Object.keys(errors).length > 0 && (
        <ul className="space-y-1 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          {Object.entries(errors).map(([k, v]) => (
            <li key={k}>
              <span className="font-medium">{k}</span>: {v}
            </li>
          ))}
        </ul>
      )}

      {summary && (
        <article className="rounded border border-[var(--line)] bg-[var(--paper)] p-5">
          <h2 className="font-[family-name:var(--font-display)] text-xl tracking-tight">
            Workflow summary
          </h2>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{summary}</p>
        </article>
      )}

      {pairs.length > 0 && (
        <article className="rounded border border-[var(--line)] bg-[var(--paper)] p-5">
          <h2 className="font-[family-name:var(--font-display)] text-xl tracking-tight">
            Action–Intent pairs
          </h2>
          <ol className="mt-4 space-y-3">
            {[...pairs]
              .sort((a, b) => a.start_t - b.start_t)
              .map((pair, index) => (
                <li
                  key={`${pair.start_t}-${pair.end_t}-${index}`}
                  className="border-b border-[var(--line)] pb-3 last:border-0"
                >
                  <p className="font-mono text-xs text-[var(--muted)]">
                    {formatTime(pair.start_t)} – {formatTime(pair.end_t)}
                  </p>
                  <p className="mt-1 text-sm">
                    <span className="text-[var(--muted)]">Action:</span> {pair.action}
                  </p>
                  <p className="mt-0.5 text-sm">
                    <span className="text-[var(--muted)]">Intent:</span> {pair.intent}
                  </p>
                  {pair.quote ? (
                    <p className="mt-0.5 text-xs italic text-[var(--muted)]">
                      “{pair.quote}”
                    </p>
                  ) : null}
                </li>
              ))}
          </ol>
        </article>
      )}

      {transcript && (
        <article className="rounded border border-[var(--line)] bg-[var(--paper)] p-5">
          <h2 className="font-[family-name:var(--font-display)] text-xl tracking-tight">
            Transcript
          </h2>
          <p className="mt-3 max-h-[240px] overflow-y-auto whitespace-pre-wrap text-sm text-[var(--muted)]">
            {transcript}
          </p>
        </article>
      )}

      {!summary && !pairs.length && !transcript && !running && (
        <p className="text-sm text-[var(--muted)]">
          No intent artifacts yet. Save selection, then run intent extraction.
        </p>
      )}
    </section>
  );
}
