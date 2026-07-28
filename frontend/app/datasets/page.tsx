import { UploadForm } from "./upload-form";
import {
  Card,
  EmptyState,
  ErrorState,
  Mono,
  PageHeader,
} from "@/components/ui";
import { api, type Dataset, type DatasetDetail } from "@/lib/api";

export const dynamic = "force-dynamic";

function DatasetCard({ dataset }: { dataset: DatasetDetail }) {
  return (
    <Card id={dataset.id} className="p-5 scroll-mt-20">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="font-medium">{dataset.name}</h2>
          {dataset.description && (
            <p className="mt-0.5 text-sm text-muted">{dataset.description}</p>
          )}
        </div>
        <span className="text-sm text-muted">
          {dataset.cases.length} case{dataset.cases.length === 1 ? "" : "s"}
        </span>
      </div>

      <ul className="mt-4 divide-y divide-line border-t border-line text-sm">
        {dataset.cases.map((c) => (
          <li key={c.id} className="grid gap-1 py-2 sm:grid-cols-2 sm:gap-4">
            <span className="wrap-anywhere">{c.input}</span>
            <span className="text-muted wrap-anywhere">→ {c.expected_output}</span>
          </li>
        ))}
      </ul>

      <div className="mt-3">
        <Mono>{dataset.id}</Mono>
      </div>
    </Card>
  );
}

export default async function DatasetsPage() {
  let datasets: Dataset[];
  try {
    datasets = await api.listDatasets();
  } catch (err) {
    return (
      <>
        <PageHeader title="Datasets" />
        <ErrorState message={(err as Error).message} />
      </>
    );
  }

  // The list endpoint returns counts only; the cases come from the detail read.
  const detailed = await Promise.all(datasets.map((d) => api.getDataset(d.id)));

  return (
    <>
      <PageHeader
        title="Datasets"
        subtitle="Inputs paired with the output you expect. Runs are evaluated against these."
      />

      <UploadForm />

      {detailed.length === 0 ? (
        <EmptyState title="No datasets yet">
          Paste a JSON document above to load one.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {detailed.map((d) => (
            <DatasetCard key={d.id} dataset={d} />
          ))}
        </div>
      )}
    </>
  );
}
