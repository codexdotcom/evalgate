"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { startRun, type FormState } from "@/lib/actions";
import type { Dataset } from "@/lib/api";
import { Card } from "@/components/ui";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
    >
      {pending ? "Running…" : "Start run"}
    </button>
  );
}

export function NewRunForm({ datasets }: { datasets: Dataset[] }) {
  const [state, formAction] = useActionState<FormState, FormData>(startRun, {});

  if (datasets.length === 0) return null;

  return (
    <Card className="mb-6 p-4">
      <form action={formAction} className="flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-56 text-sm">
          <span className="mb-1 block font-medium">Dataset</span>
          <select
            name="dataset_id"
            className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.case_count ?? 0} cases)
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="mb-1 block font-medium">Scorer</span>
          <select
            name="scorer"
            defaultValue="llm_judge"
            className="rounded-md border border-line bg-white px-3 py-2 text-sm"
          >
            <option value="llm_judge">LLM judge</option>
            <option value="exact_match">Exact match</option>
          </select>
        </label>

        <label className="text-sm">
          <span className="mb-1 block font-medium">Confidence threshold</span>
          <input
            name="confidence_threshold"
            type="number"
            step="0.05"
            min="0"
            max="1"
            defaultValue="0.75"
            className="w-32 rounded-md border border-line bg-white px-3 py-2 text-sm tabular-nums"
          />
        </label>

        <SubmitButton />
      </form>

      {state.error && (
        <p className="mt-3 text-sm text-rose-700">{state.error}</p>
      )}
      <p className="mt-3 text-xs text-muted">
        Judgments below the threshold are escalated to the review queue instead
        of being scored automatically.
      </p>
    </Card>
  );
}
