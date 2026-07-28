/**
 * Server-side client for the EvalGate API.
 *
 * Every read runs on the Next server, so the browser never talks to FastAPI
 * directly and there is no CORS surface to configure.
 */

export const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

export type Verdict = "pass" | "fail" | "needs_review";
export type RunStatus = "pending" | "running" | "completed" | "failed";
export type Gate = "pass" | "fail" | "blocked";

export interface EvalCase {
  id: string;
  input: string;
  expected_output: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface Dataset {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  case_count: number | null;
}

export interface DatasetDetail extends Dataset {
  cases: EvalCase[];
}

export interface Run {
  id: string;
  dataset_id: string;
  model: string;
  scorer: string;
  confidence_threshold: number;
  status: RunStatus;
  created_at: string;
  completed_at: string | null;
}

export interface Result {
  id: string;
  run_id: string;
  case_id: string;
  model_output: string;
  score: number;
  confidence: number;
  verdict: Verdict;
  reasoning: string | null;
  scorer: string;
  created_at: string;
}

export interface ReviewItem {
  id: string;
  result_id: string;
  status: "pending" | "resolved";
  human_verdict: Verdict | null;
  reviewer: string | null;
  notes: string | null;
  created_at: string;
  resolved_at: string | null;
  input: string;
  expected_output: string;
  model_output: string;
  score: number;
  confidence: number;
  reasoning: string | null;
}

export interface ReportSummary {
  total: number;
  pass: number;
  fail: number;
  needs_review: number;
  pass_rate: number;
  decided_pass_rate: number;
  human_reviewed: number;
  gate: Gate;
  gate_pass_rate: number;
}

export interface Report {
  id: string;
  run_id: string;
  summary: ReportSummary;
  content_hash: string;
  generated_at: string;
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is it running?`);
  }

  if (!resp.ok) {
    const body = await resp.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      /* not JSON; the raw body is the best message we have */
    }
    throw new ApiError(resp.status, detail);
  }
  return resp.status === 204 ? (undefined as T) : resp.json();
}

/** Returns null on 404 rather than throwing, for the many optional reads. */
async function optional<T>(path: string): Promise<T | null> {
  try {
    return await request<T>(path);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export const api = {
  listDatasets: () => request<Dataset[]>("/datasets"),
  getDataset: (id: string) => request<DatasetDetail>(`/datasets/${id}`),
  createDataset: (body: unknown) =>
    request<DatasetDetail>("/datasets", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listRuns: () => request<Run[]>("/runs"),
  getRun: (id: string) => request<Run>(`/runs/${id}`),
  getResults: (id: string) => request<Result[]>(`/runs/${id}/results`),
  createRun: (body: unknown) =>
    request<Run>("/runs", { method: "POST", body: JSON.stringify(body) }),

  getReport: (runId: string) => optional<Report>(`/runs/${runId}/report`),
  createReport: (runId: string) =>
    request<Report>(`/runs/${runId}/report`, { method: "POST" }),

  listReview: (status: "pending" | "all" = "pending") =>
    request<ReviewItem[]>(`/review?status=${status}`),
  resolveReview: (id: string, body: unknown) =>
    request<unknown>(`/review/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
