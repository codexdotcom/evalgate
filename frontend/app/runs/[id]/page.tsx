import Link from "next/link";
import { notFound } from "next/navigation";

import { GenerateReportButton } from "./generate-report-button";
import {
  Card,
  ErrorState,
  GateBadge,
  Mono,
  PageHeader,
  Stat,
  StatusBadge,
  VerdictBadge,
} from "@/components/ui";
import { ApiError, api, type EvalCase } from "@/lib/api";

export const dynamic = "force-dynamic";

const GATE_EXPLANATION: Record<string, string> = {
  pass: "Pass rate cleared the configured bar and nothing is awaiting a human.",
  fail: "Pass rate fell short of the configured bar.",
  blocked:
    "Cannot certify: the judge was not confident enough on at least one case and a human has not ruled yet.",
};

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let run, results, report;
  try {
    run = await api.getRun(id);
    [results, report] = await Promise.all([
      api.getResults(id),
      api.getReport(id),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    return (
      <>
        <PageHeader title="Run" />
        <ErrorState message={(err as Error).message} />
      </>
    );
  }

  // Results store only a case_id; the prompt and expected answer live on the
  // dataset, so join them here rather than widening the results endpoint.
  const dataset = await api.getDataset(run.dataset_id);
  const caseById = new Map<string, EvalCase>(dataset.cases.map((c) => [c.id, c]));

  const summary = report?.summary;

  return (
    <>
      <PageHeader
        title={`Run ${run.id.slice(0, 8)}`}
        subtitle={`${dataset.name} · ${run.scorer} · confidence threshold ${run.confidence_threshold}`}
        action={<GenerateReportButton runId={run.id} hasReport={!!report} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <StatusBadge status={run.status} />
        {summary && <GateBadge gate={summary.gate} />}
        <Mono>{run.model}</Mono>
      </div>

      {summary ? (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Stat label="Cases" value={summary.total} />
            <Stat label="Passed" value={summary.pass} />
            <Stat label="Failed" value={summary.fail} />
            <Stat label="Needs review" value={summary.needs_review} />
            <Stat
              label="Pass rate"
              value={`${(summary.pass_rate * 100).toFixed(0)}%`}
              hint={`bar: ${(summary.gate_pass_rate * 100).toFixed(0)}%`}
            />
          </div>
          <Card className="mb-6 px-4 py-3">
            <p className="text-sm">{GATE_EXPLANATION[summary.gate]}</p>
            <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
              <span>
                Decided pass rate:{" "}
                <span className="tabular-nums">
                  {(summary.decided_pass_rate * 100).toFixed(0)}%
                </span>
              </span>
              <span>Human-reviewed verdicts: {summary.human_reviewed}</span>
              <span>
                Report hash: <Mono>{report!.content_hash}</Mono>
              </span>
            </div>
          </Card>
        </>
      ) : (
        <Card className="mb-6 px-4 py-3 text-sm text-muted">
          No report yet. Generating one freezes these verdicts into a hashed,
          auditable record.
        </Card>
      )}

      {summary && summary.needs_review > 0 && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {summary.needs_review} case{summary.needs_review === 1 ? "" : "s"}{" "}
          awaiting a human decision.{" "}
          <Link href="/review" className="font-medium underline">
            Open the review queue
          </Link>
        </div>
      )}

      <Card className="overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Input</th>
              <th className="px-4 py-2 font-medium">Expected</th>
              <th className="px-4 py-2 font-medium">Model output</th>
              <th className="px-4 py-2 font-medium">Score</th>
              <th className="px-4 py-2 font-medium">Conf.</th>
              <th className="px-4 py-2 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => {
              const c = caseById.get(r.case_id);
              const escalated = r.confidence < run.confidence_threshold;
              return (
                <tr key={r.id} className="border-t border-line align-top">
                  <td className="max-w-56 px-4 py-3 wrap-anywhere">
                    {c?.input ?? <Mono>{r.case_id}</Mono>}
                  </td>
                  <td className="max-w-48 px-4 py-3 text-muted wrap-anywhere">
                    {c?.expected_output ?? "—"}
                  </td>
                  <td className="max-w-64 px-4 py-3 wrap-anywhere">
                    {r.model_output || <span className="text-muted">—</span>}
                    {r.reasoning && (
                      <div className="mt-1 text-xs text-muted wrap-anywhere">
                        {r.reasoning}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{r.score.toFixed(2)}</td>
                  <td
                    className={`px-4 py-3 tabular-nums ${escalated ? "font-semibold text-amber-700" : ""}`}
                  >
                    {r.confidence.toFixed(2)}
                  </td>
                  <td className="px-4 py-3">
                    <VerdictBadge verdict={r.verdict} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </>
  );
}
