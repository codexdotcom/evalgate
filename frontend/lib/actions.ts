"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, api } from "./api";

export interface FormState {
  error?: string;
  ok?: string;
}

function message(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : "Something went wrong.";
}

export async function resolveReview(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const id = String(formData.get("id"));
  const reviewer = String(formData.get("reviewer") ?? "").trim();
  const verdict = String(formData.get("verdict"));

  if (!reviewer) return { error: "Reviewer name is required." };

  try {
    await api.resolveReview(id, {
      verdict,
      reviewer,
      notes: String(formData.get("notes") ?? "").trim() || null,
    });
  } catch (err) {
    return { error: message(err) };
  }

  revalidatePath("/review");
  revalidatePath("/");
  return { ok: `Recorded as ${verdict}.` };
}

export async function startRun(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const threshold = Number(formData.get("confidence_threshold"));
  if (Number.isNaN(threshold) || threshold < 0 || threshold > 1) {
    return { error: "Confidence threshold must be between 0 and 1." };
  }

  let runId: string;
  try {
    const run = await api.createRun({
      dataset_id: String(formData.get("dataset_id")),
      scorer: String(formData.get("scorer")),
      confidence_threshold: threshold,
    });
    runId = run.id;
  } catch (err) {
    return { error: message(err) };
  }

  revalidatePath("/");
  // redirect() signals by throwing, so it must sit outside the try block.
  redirect(`/runs/${runId}`);
}

export async function generateReport(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const runId = String(formData.get("run_id"));
  try {
    await api.createReport(runId);
  } catch (err) {
    return { error: message(err) };
  }
  revalidatePath(`/runs/${runId}`);
  return { ok: "Report generated." };
}

export async function uploadDataset(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const raw = String(formData.get("json") ?? "").trim();
  if (!raw) return { error: "Paste a dataset JSON document." };

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { error: "That is not valid JSON." };
  }

  const doc = parsed as { name?: unknown; cases?: unknown };
  if (typeof doc.name !== "string" || !doc.name.trim()) {
    return { error: 'Dataset needs a non-empty "name".' };
  }
  if (!Array.isArray(doc.cases) || doc.cases.length === 0) {
    return { error: 'Dataset needs a non-empty "cases" array.' };
  }

  let datasetId: string;
  try {
    const created = await api.createDataset(parsed);
    datasetId = created.id;
  } catch (err) {
    return { error: message(err) };
  }

  revalidatePath("/datasets");
  redirect(`/datasets#${datasetId}`);
}
