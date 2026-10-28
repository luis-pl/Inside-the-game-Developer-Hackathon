type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordValue)
    : {};
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const string = (value: unknown) => (typeof value === "string" ? value : "");
const statusName: Record<string, string> = {
  complete: "Complete",
  partial: "Partial",
  error: "Interrupted",
  needs_clarification: "More detail needed",
  unsupported: "Unavailable",
};

/** Optional trace fields stay unknown; absence is not a completed or skipped step. */
export function runActivity(value: unknown) {
  const run = record(value),
    plan = record(run.delegation);
  const data = record(run.data),
    analysis = record(run.analysis),
    insights = record(run.insights);
  const evidence = list(data.evidence_catalog).map(record);
  const rows = [
    {
      name: "Interpreter",
      detail: string(plan.reply) || "Identifies the question and its scope.",
      status: string(plan.action)
        ? ({
            create: "New report",
            modify: "Report update",
            answer: "Question answered",
            clarify: "More detail needed",
            catalog: "Match catalogue",
          }[string(plan.action)] ?? string(plan.action))
        : "Not recorded",
      count: null,
    },
    {
      name: "Data agent",
      detail: "Retrieves evidence from the available football data.",
      status: statusName[string(data.status)] ?? "Not recorded",
      count: Array.isArray(data.evidence_catalog)
        ? `${evidence.length} evidence sources`
        : null,
    },
    {
      name: "Sports analyst",
      detail: "Interprets the evidence and states its limits.",
      status: statusName[string(analysis.status)] ?? "Not recorded",
      count: Array.isArray(analysis.facts)
        ? `${analysis.facts.length} referenced facts`
        : null,
    },
    {
      name: "Insights agent",
      detail: "Builds the visual report and preserves its sources.",
      status: statusName[string(insights.status)] ?? "Not recorded",
      count: Array.isArray(insights.blocks)
        ? `${insights.blocks.length} report blocks`
        : null,
    },
  ];
  const errors = [
    run.error,
    ...list(data.issues),
    ...list(analysis.issues),
    ...list(insights.issues),
  ]
    .map((issue) => string(issue) || string(record(issue).code))
    .filter(Boolean);
  return {
    request: string(record(run.input).text),
    id: string(run.request_id),
    elapsedMs:
      typeof run.elapsed_ms === "number" && Number.isFinite(run.elapsed_ms)
        ? run.elapsed_ms
        : null,
    rows,
    errors: [...new Set(errors)],
    evidence: evidence.map((e) => ({
      id: string(e.evidence_id),
      operation: string(e.operation),
      arguments: record(e.arguments),
    })),
  };
}
