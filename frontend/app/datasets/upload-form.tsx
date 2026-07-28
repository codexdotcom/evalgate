"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { uploadDataset, type FormState } from "@/lib/actions";
import { Card } from "@/components/ui";

const PLACEHOLDER = `{
  "name": "Support replies",
  "description": "Golden answers for tier-1 questions",
  "cases": [
    { "input": "What is the capital of France?", "expected_output": "Paris" }
  ]
}`;

function Submit() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
    >
      {pending ? "Loading…" : "Load dataset"}
    </button>
  );
}

export function UploadForm() {
  const [state, formAction] = useActionState<FormState, FormData>(
    uploadDataset,
    {},
  );

  return (
    <Card className="mb-6 p-4">
      <form action={formAction}>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Dataset JSON</span>
          <textarea
            name="json"
            rows={8}
            spellCheck={false}
            placeholder={PLACEHOLDER}
            className="w-full rounded-md border border-line bg-white px-3 py-2 font-mono text-xs"
          />
        </label>
        <div className="mt-3 flex items-center gap-3">
          <Submit />
          <span className="text-xs text-muted">
            Same shape as <code>backend/sample_dataset.json</code>.
          </span>
        </div>
      </form>
      {state.error && <p className="mt-2 text-sm text-rose-700">{state.error}</p>}
    </Card>
  );
}
