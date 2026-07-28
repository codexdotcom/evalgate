"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { generateReport, type FormState } from "@/lib/actions";

function Submit({ label }: { label: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md border border-line bg-white px-3 py-1.5 text-sm font-medium transition hover:bg-slate-50 disabled:opacity-50"
    >
      {pending ? "Generating…" : label}
    </button>
  );
}

export function GenerateReportButton({
  runId,
  hasReport,
}: {
  runId: string;
  hasReport: boolean;
}) {
  const [state, formAction] = useActionState<FormState, FormData>(
    generateReport,
    {},
  );

  return (
    <div className="flex flex-col items-end gap-1">
      <form action={formAction}>
        <input type="hidden" name="run_id" value={runId} />
        <Submit label={hasReport ? "Regenerate report" : "Generate report"} />
      </form>
      {state.error && <p className="text-xs text-rose-700">{state.error}</p>}
    </div>
  );
}
