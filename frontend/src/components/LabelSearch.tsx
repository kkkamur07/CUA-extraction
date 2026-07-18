"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

type Props = {
  value: string;
  onChange: (value: string) => void;
  knownLabels: string[];
  counts?: Record<string, number>;
};

export function LabelSearch({ value, onChange, knownLabels, counts = {} }: Props) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const query = value.trim().toLowerCase();

  const options = useMemo(() => {
    const unique = Array.from(new Set(knownLabels.map((label) => label.trim()).filter(Boolean)));
    const filtered = unique
      .filter((label) => !query || label.toLowerCase().includes(query))
      .sort((a, b) => {
        const aExact = a.toLowerCase() === query ? 0 : 1;
        const bExact = b.toLowerCase() === query ? 0 : 1;
        if (aExact !== bExact) return aExact - bExact;
        return (counts[b] ?? 0) - (counts[a] ?? 0) || a.localeCompare(b);
      });

    const exactExists = unique.some((label) => label.toLowerCase() === query);
    const createOption =
      query && !exactExists
        ? [{ kind: "create" as const, label: value.trim() }]
        : [];

    return [
      ...filtered.map((label) => ({ kind: "existing" as const, label })),
      ...createOption,
    ];
  }, [counts, knownLabels, query, value]);

  const activeHighlight =
    options.length === 0 ? 0 : Math.min(highlight, options.length - 1);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, []);

  const pick = (next: string) => {
    onChange(next);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative block text-sm">
      <span className="text-xs uppercase tracking-wide text-[var(--muted)]">Label</span>
      <input
        value={value}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="Search or add a label"
        onFocus={() => {
          setHighlight(0);
          setOpen(true);
        }}
        onChange={(event) => {
          onChange(event.target.value);
          setHighlight(0);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setHighlight((index) => Math.min(options.length - 1, index + 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setHighlight((index) => Math.max(0, index - 1));
          } else if (event.key === "Enter" && open && options[activeHighlight]) {
            event.preventDefault();
            pick(options[activeHighlight].label);
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
        className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
      />

      {open && options.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-48 w-full overflow-auto rounded border border-[var(--line)] bg-[var(--paper)] shadow-sm"
        >
          {options.map((option, index) => (
            <li key={`${option.kind}-${option.label}`} role="option" aria-selected={index === activeHighlight}>
              <button
                type="button"
                onMouseEnter={() => setHighlight(index)}
                onClick={() => pick(option.label)}
                className={`flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-xs ${
                  index === activeHighlight ? "bg-[var(--wash)]" : ""
                }`}
              >
                <span>
                  {option.kind === "create" ? (
                    <>
                      Add <span className="font-medium">{option.label}</span>
                    </>
                  ) : (
                    option.label
                  )}
                </span>
                {option.kind === "existing" && (
                  <span className="font-mono text-[var(--muted)]">{counts[option.label] ?? 0}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
