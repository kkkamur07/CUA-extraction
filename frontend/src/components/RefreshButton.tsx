"use client";

import { useRouter } from "next/navigation";

export function RefreshButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => router.refresh()}
      className="rounded border border-[var(--line)] bg-[var(--wash)] px-3 py-1.5 text-sm"
    >
      Refresh
    </button>
  );
}
