export type ChangedBlock = { id: string; title: string; insight_id: string };
export type ReportChanges = {
  id?: string;
  revision: number;
  added: ChangedBlock[];
  updated: ChangedBlock[];
  removed: ChangedBlock[];
  title_changed: boolean;
  analysis_updated: boolean;
};

export function reportLinkLabel(runs: unknown[]) {
  const run = runs.at(-1) as { delegation?: { action?: string } } | undefined;
  return ["create", "modify"].includes(run?.delegation?.action ?? "")
    ? "View update"
    : "View report";
}

export function hasScopedAnalysis(runs: unknown[]) {
  const run = runs.at(-1) as
    | {
        analysis?: { status?: string; issues?: unknown[] };
        insights?: { status?: string };
      }
    | undefined;
  return (
    run?.analysis?.status === "partial" &&
    run.analysis.issues?.length === 0 &&
    run.insights?.status === "complete"
  );
}

export function changedIds(changes: ReportChanges | null | undefined) {
  return [
    ...new Set(
      [...(changes?.added ?? []), ...(changes?.updated ?? [])].map((b) => b.id),
    ),
  ].filter((id) => /^[\w-]{1,120}$/.test(id));
}
export function changeLabel(changes: ReportChanges) {
  const parts = [];
  if (changes.added.length)
    parts.push(
      `${changes.added.length} ${changes.added.length === 1 ? "chart added" : "charts added"}`,
    );
  if (changes.updated.length)
    parts.push(
      `${changes.updated.length} ${changes.updated.length === 1 ? "chart updated" : "charts updated"}`,
    );
  if (changes.removed.length)
    parts.push(
      `${changes.removed.length} ${changes.removed.length === 1 ? "chart removed" : "charts removed"}`,
    );
  if (!parts.length && changes.title_changed) parts.push("Title updated");
  if (!parts.length && changes.analysis_updated) parts.push("Analysis updated");
  return parts.join(" · ") || "Report updated";
}
export function friendlyIssue(code: string) {
  if (code.startsWith("MODEL_"))
    return "The model could not finish this update. You can retry; your current report is still available.";
  if (/TIMEOUT|DEADLINE/.test(code))
    return "This took longer than expected. You can retry; your current report is still available.";
  if (/UNAUTHORIZED|SESSION_EXPIRED/.test(code))
    return "Your session has expired. Sign in again to continue.";
  if (/RATE|BUSY|CAPACITY/.test(code))
    return "Several requests are running. Wait a moment and try again.";
  if (/EVIDENCE|CATALOG/.test(code))
    return "The required evidence could not be retrieved. Check the match or try again.";
  return "The request was not completed. Try again or provide more detail.";
}
export function clampPanel(
  width: number,
  available: number,
  kind: "chat" | "history",
) {
  const min = kind === "chat" ? 250 : 170;
  const max = Math.max(
    min,
    Math.min(
      kind === "chat" ? 620 : 300,
      available - (kind === "chat" ? 290 : 700),
    ),
  );
  return Math.round(
    Math.min(max, Math.max(min, Number.isFinite(width) ? width : min)),
  );
}
