import { useParams } from "react-router-dom";
import { useRunDetailQuery, useRecomputeCalibrationMutation } from "../app/api";

const band = (k: number) =>
  k >= 0.8 ? "Strong" : k >= 0.6 ? "Usable" : k >= 0.4 ? "Weak" : "Do not trust";

export function RunDetail() {
  const { runId = "" } = useParams();
  const { data } = useRunDetailQuery(runId, { pollingInterval: 4000 });
  const [recompute, { isLoading }] = useRecomputeCalibrationMutation();
  if (!data) return <div className="pad">Loading…</div>;

  const { run, scoreSummary, calibrations } = data;
  const cal = new Map(calibrations.map((c: any) => [c.scorerKey, c]));

  return (
    <div className="pad">
      <h2>{run.model}</h2>
      <p>
        {run.doneCases}/{run.totalCases} trajectories · ${run.costUsd.toFixed(3)} · {run.status}
      </p>
     <button onClick={() => recompute({ runId })} disabled={isLoading}>
  Recompute calibration
</button>
<button onClick={() => recompute({ runId, blindOnly: true })} disabled={isLoading}>
  Recompute (blind labels only)
</button>

      <table className="grid">
        <thead>
          <tr>
            <th>Scorer</th><th>Pass rate</th><th>Avg conf</th>
            <th>Human n</th><th>Agreement</th><th>Kappa</th>
            <th>False pass</th><th>False fail</th><th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {scoreSummary.map((s: any) => {
            const c: any = cal.get(s.scorerKey);
            return (
              <tr key={s.scorerKey}>
                <td>{s.scorerKey}</td>
                <td>{(s.passRate * 100).toFixed(1)}%</td>
                <td>{s.avgConfidence.toFixed(2)}</td>
                <td>{c?.n ?? "-"}</td>
                <td>{c ? (c.agreement * 100).toFixed(1) + "%" : "-"}</td>
                <td className={c && c.kappa < 0.6 ? "bad" : "good"}>
                  {c ? c.kappa.toFixed(2) : "-"}
                </td>
                <td className={c?.falsePass ? "bad" : ""}>{c?.falsePass ?? "-"}</td>
                <td>{c?.falseFail ?? "-"}</td>
                <td>{c ? band(c.kappa) : "unlabeled"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="note">
        False passes are the expensive error: the judge cleared a trajectory a human rejected.
        A scorer below 0.6 kappa should gate nothing.
      </p>
    </div>
  );
}