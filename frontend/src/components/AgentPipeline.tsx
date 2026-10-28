/** Only reported stages are active; no simulated completion percentages. */
export function AgentPipeline({
  stage,
  busy,
  match,
  disconnected = false,
}: {
  stage?: string;
  busy: boolean;
  match?: string;
  disconnected?: boolean;
}) {
  const steps = [
    {
      name: "Interpreter",
      task: "Understands your brief",
      stages: ["queued", "catalog", "interpreting"],
    },
    { name: "Data agent", task: "Retrieves match evidence", stages: ["data"] },
    {
      name: "Analyst + Insights",
      task: "Build findings & charts",
      stages: ["analysis", "editing"],
    },
  ];
  const status = disconnected
    ? "Connection lost · recover status"
    : busy
      ? "Agents working"
      : stage === "complete"
        ? "Request complete"
        : stage === "partial"
          ? "Partial results · review scope"
          : stage === "error"
            ? "Request interrupted"
            : stage === "clarification"
              ? "Your input is needed"
              : "Ready for your brief";
  return (
    <section className="agent-context" aria-label="Agent workflow">
      <div className="agent-context-title">
        <span className="context-label">MATCH CONTEXT</span>
        <strong title={match}>{match ?? "Choose a match to begin"}</strong>
        <span
          className={`agent-status ${busy ? "is-working" : ""}`}
          role="status"
        >
          <i />
          {status}
        </span>
      </div>
      <ol className="agent-pipeline">
        {steps.map((step, i) => (
          <li
            key={step.name}
            data-active={busy && step.stages.includes(stage ?? "")}
          >
            <span className="pipeline-number">0{i + 1}</span>
            <div>
              <strong>{step.name}</strong>
              <small>{step.task}</small>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
