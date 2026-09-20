import { useEffect, useMemo } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useReviewQueueQuery, useSubmitReviewMutation } from "../app/api";
import { label, back, toggleBlind, selectRate } from "../features/review/reviewSlice";
import type { RootState } from "../app/store";
import { TrajectoryTimeline } from "../components/TrajectoryTimeline";

export function ReviewQueue() {
  const dispatch = useDispatch();
  const { data, refetch, isFetching } = useReviewQueueQuery(100);
  const [submit] = useSubmitReviewMutation();
  const { cursor, reviewer, sessionCount, blindMode, labeled } = useSelector(
    (s: RootState) => s.review,
  );
  const rate = useSelector(selectRate);

  const items = data?.reviewQueue ?? [];
  const current = items[cursor];
  const remaining = items.length - cursor;

  // Only reveal scores after the human has committed, and only in blind mode.
  const alreadyLabeled = current ? current.id in labeled : false;
  const showScores = !blindMode || alreadyLabeled;

  const act = useMemo(
    () => (passed: boolean) => {
      if (!current) return;
      dispatch(label({ id: current.id, passed }));
      submit({
        trajectoryId: current.id,
        humanPassed: passed,
        reviewer,
        blind: blindMode,
      });
    },
    [current, dispatch, submit, reviewer, blindMode],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "p" || e.key === "j") act(true);
      else if (e.key === "f" || e.key === "k") act(false);
      else if (e.key === "u") dispatch(back());
      else if (e.key === "b") dispatch(toggleBlind());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act, dispatch]);

  useEffect(() => {
    if (remaining < 15 && !isFetching) refetch();
  }, [remaining, isFetching, refetch]);

  if (!current) {
    return <div className="pad">Queue empty. {sessionCount} labeled this session.</div>;
  }

  const judge = current.scores.find((s: any) => s.scorerKind === "llm_judge");

  return (
    <div className="review">
      <header className="review__bar">
        <span>{remaining} left</span>
        <span>{sessionCount} labeled</span>
        <span>{rate.toFixed(1)}/min</span>
        <button
          className={blindMode ? "toggle toggle--on" : "toggle"}
          onClick={() => dispatch(toggleBlind())}
        >
          {blindMode ? "Blind: on" : "Blind: off"}
        </button>
        <span className="hint">p pass · f fail · u undo · b blind</span>
      </header>

      {blindMode && !alreadyLabeled && (
        <div className="banner">
          Scorer verdicts hidden until you label. These labels are the ones
          calibration should trust.
        </div>
      )}

      <section className="review__task">
        <h3>{current.taskCase.externalId}</h3>
        <p className="prompt">{current.taskCase.prompt}</p>
        {current.taskCase.rubric && <p className="rubric">Rubric: {current.taskCase.rubric}</p>}
      </section>

      <TrajectoryTimeline steps={current.steps} />

      <section className="review__final">
        <h4>Final output ({current.terminalState})</h4>
        <pre>{current.finalOutput}</pre>
      </section>

      {showScores ? (
        <section className="review__scores">
          {current.scores.map((s: any) => (
            <div key={s.scorerKey} className={s.passed ? "chip chip--pass" : "chip chip--fail"}>
              <strong>{s.scorerKey}</strong> {s.passed ? "pass" : "fail"}
              <em> conf {s.confidence.toFixed(2)}</em>
            </div>
          ))}
          {judge?.rationale && <p className="rationale">Judge: {judge.rationale}</p>}
        </section>
      ) : (
        <section className="review__scores review__scores--hidden">
          {current.scores.length} scorer verdicts hidden
        </section>
      )}

      <footer className="review__actions">
        <button onClick={() => act(true)}>Pass (p)</button>
        <button onClick={() => act(false)}>Fail (f)</button>
        <button onClick={() => dispatch(back())}>Undo (u)</button>
      </footer>
    </div>
  );
}