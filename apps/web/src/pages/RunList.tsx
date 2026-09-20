import { Link } from "react-router-dom";
import { useRunsQuery } from "../app/api";

export function RunList() {
  const { data, isLoading } = useRunsQuery(undefined, { pollingInterval: 5000 });
  if (isLoading) return <div className="pad">Loading…</div>;

  const runs = data?.runs ?? [];
  if (!runs.length) return <div className="pad">No runs yet.</div>;

  return (
    <div className="pad">
      <h2>Runs</h2>
      <table className="grid">
        <thead>
          <tr>
            <th>Model</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Cost</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r: any) => {
            const pct = r.totalCases ? (r.doneCases / r.totalCases) * 100 : 0;
            return (
              <tr key={r.id}>
                <td>
                  <Link to={`/runs/${r.id}`}>{r.model}</Link>
                </td>
                <td>{r.status}</td>
                <td>
                  <div className="bar">
                    <span style={{ width: `${pct}%` }} />
                  </div>
                  {r.doneCases}/{r.totalCases}
                </td>
                <td>${r.costUsd.toFixed(3)}</td>
                <td>{new Date(r.startedAt).toLocaleString()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}