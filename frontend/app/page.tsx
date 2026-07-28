import Link from "next/link";

import { NewRunForm } from "./new-run-form";
import {
  Card,
  EmptyState,
  ErrorState,
  GateBadge,
  Mono,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { api, type Dataset, type Report, type Run } from "@/lib/api";

export const dynamic = "force-dynamic";

function when(iso: string) {
  return new Date(iso).toLocaleString();
}

function RunRow({ run, report }: { run: Run; report: Report | null }) {
  return (
    <tr className="border-t border-line hover:bg-slate-50">
      <td className="px-4 py-3">
        <Link
          href={`/runs/${run.id}`}
          className="font-medium text-sky-700 hover:underline"
        >
          {run.id.slice(0, 8)}
        </Link>
        <div className="text-xs text-muted">{when(run.created_at)}</div>
      </td>
      <td className="px-4 py-3">
        <Mono>{run.model}</Mono>
      </td>
      <td className="px-4 py-3 text-sm">{run.scorer}</td>
      <td className="px-4 py-3">
        <StatusBadge status={run.status} />
      </td>
      <td className="px-4 py-3 text-sm tabular-nums">
        {report ? `${(report.summary.pass_rate * 100).toFixed(0)}%` : "—"}
      </td>
      <td className="px-4 py-3">
        {report ? (
          <GateBadge gate={report.summary.gate} />
        ) : (
          <span className="text-xs text-muted">no report</span>
        )}
      </td>
    </tr>
  );
}

export default async function RunsPage() {
  let runs: Run[];
  let datasets: Dataset[];
  try {
    [runs, datasets] = await Promise.all([api.listRuns(), api.listDatasets()]);
  } catch (err) {
    return (
      <>
        <PageHeader title="Runs" />
        <ErrorState message={(err as Error).message} />
      </>
    );
  }

  // A run only has a report once someone asks for one, so these are optional
  // reads that resolve to null rather than throwing.
  const reports = await Promise.all(runs.map((r) => api.getReport(r.id)));

  return (
    <>
      <PageHeader
        title="Runs"
        subtitle="Every evaluation executed against a dataset, and whether it cleared the gate."
      />

      <NewRunForm datasets={datasets} />

      {runs.length === 0 ? (
        <EmptyState title="No runs yet">
          {datasets.length === 0 ? (
            <>
              Load a dataset from the{" "}
              <Link href="/datasets" className="text-sky-700 hover:underline">
                Datasets
              </Link>{" "}
              page first.
            </>
          ) : (
            "Start one with the form above."
          )}
        </EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Run</th>
                <th className="px-4 py-2 font-medium">Model</th>
                <th className="px-4 py-2 font-medium">Scorer</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Pass rate</th>
                <th className="px-4 py-2 font-medium">Gate</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, i) => (
                <RunRow key={run.id} run={run} report={reports[i]} />
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
