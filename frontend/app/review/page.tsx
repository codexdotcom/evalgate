import { ResolveForm } from "./resolve-form";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  VerdictBadge,
} from "@/components/ui";
import { api, type ReviewItem } from "@/lib/api";

export const dynamic = "force-dynamic";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </div>
      <p className="mt-1 text-sm wrap-anywhere">
        {value || <span className="text-muted">—</span>}
      </p>
    </div>
  );
}

function QueueCard({ item }: { item: ReviewItem }) {
  const resolved = item.status === "resolved";

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge tone="amber">confidence {item.confidence.toFixed(2)}</Badge>
        <Badge tone="slate">score {item.score.toFixed(2)}</Badge>
        {resolved && item.human_verdict && (
          <>
            <VerdictBadge verdict={item.human_verdict} />
            <span className="text-xs text-muted">
              by {item.reviewer}
              {item.notes ? ` — ${item.notes}` : ""}
            </span>
          </>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Input" value={item.input} />
        <Field label="Expected" value={item.expected_output} />
        <Field label="Model output" value={item.model_output} />
      </div>

      {item.reasoning && (
        <div className="mt-4 rounded-lg bg-slate-50 px-3 py-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted">
            Judge reasoning
          </div>
          <p className="mt-1 text-sm wrap-anywhere">{item.reasoning}</p>
        </div>
      )}

      {!resolved && <ResolveForm id={item.id} />}
    </Card>
  );
}

export default async function ReviewPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const showAll = status === "all";

  let items: ReviewItem[];
  try {
    items = await api.listReview(showAll ? "all" : "pending");
  } catch (err) {
    return (
      <>
        <PageHeader title="Review queue" />
        <ErrorState message={(err as Error).message} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Review queue"
        subtitle="Cases the judge was not confident enough to decide on its own."
        action={
          <a
            href={showAll ? "/review" : "/review?status=all"}
            className="rounded-md border border-line bg-white px-3 py-1.5 text-sm font-medium transition hover:bg-slate-50"
          >
            {showAll ? "Show pending only" : "Show resolved too"}
          </a>
        }
      />

      {items.length === 0 ? (
        <EmptyState title={showAll ? "Nothing here yet" : "Queue is clear"}>
          {showAll
            ? "Run an evaluation to populate the queue."
            : "Every judgment so far cleared its confidence threshold."}
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <QueueCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </>
  );
}
