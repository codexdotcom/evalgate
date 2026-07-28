"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { resolveReview, type FormState } from "@/lib/actions";

function Buttons() {
  const { pending } = useFormStatus();
  return (
    <div className="flex gap-2">
      <button
        type="submit"
        name="verdict"
        value="pass"
        disabled={pending}
        className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
      >
        Mark pass
      </button>
      <button
        type="submit"
        name="verdict"
        value="fail"
        disabled={pending}
        className="rounded-md bg-rose-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-rose-700 disabled:opacity-50"
      >
        Mark fail
      </button>
    </div>
  );
}

export function ResolveForm({ id }: { id: string }) {
  const [state, formAction] = useActionState<FormState, FormData>(
    resolveReview,
    {},
  );

  return (
    <form action={formAction} className="mt-4 border-t border-line pt-4">
      <input type="hidden" name="id" value={id} />
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block font-medium">Reviewer</span>
          <input
            name="reviewer"
            required
            placeholder="your name"
            className="rounded-md border border-line bg-white px-3 py-1.5 text-sm"
          />
        </label>
        <label className="flex-1 min-w-48 text-sm">
          <span className="mb-1 block font-medium">
            Notes <span className="font-normal text-muted">(optional)</span>
          </span>
          <input
            name="notes"
            placeholder="why this call"
            className="w-full rounded-md border border-line bg-white px-3 py-1.5 text-sm"
          />
        </label>
        <Buttons />
      </div>
      {state.error && <p className="mt-2 text-sm text-rose-700">{state.error}</p>}
      {state.ok && <p className="mt-2 text-sm text-emerald-700">{state.ok}</p>}
    </form>
  );
}
