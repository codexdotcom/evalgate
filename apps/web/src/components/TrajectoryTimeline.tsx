export function TrajectoryTimeline({ steps }: { steps: any[] }) {
  return (
    <ol className="timeline">
      {steps.map((s) => (
        <li key={s.index} className={`timeline__step timeline__step--${s.role}`}>
          <div className="timeline__meta">
            <span className="role">{s.role}</span>
            <span className="lat">{s.latencyMs}ms</span>
            <span className="tok">{s.inputTokens + s.outputTokens} tok</span>
          </div>
          {s.content && <p className="content">{s.content}</p>}
          {s.toolCalls?.map((tc: any) => (
            <div key={tc.id} className="toolcall">
              <code>{tc.name}({JSON.stringify(tc.args).slice(0, 160)})</code>
            </div>
          ))}
          {s.toolResult && <pre className="toolresult">{s.toolResult.slice(0, 400)}</pre>}
        </li>
      ))}
    </ol>
  );
}