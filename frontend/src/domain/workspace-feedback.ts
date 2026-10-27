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
    ? "Ver la actualización"
    : "Ver el informe";
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
      `${changes.added.length} ${changes.added.length === 1 ? "gráfico añadido" : "gráficos añadidos"}`,
    );
  if (changes.updated.length)
    parts.push(
      `${changes.updated.length} ${changes.updated.length === 1 ? "gráfico actualizado" : "gráficos actualizados"}`,
    );
  if (changes.removed.length)
    parts.push(
      `${changes.removed.length} ${changes.removed.length === 1 ? "gráfico retirado" : "gráficos retirados"}`,
    );
  if (!parts.length && changes.title_changed) parts.push("Título actualizado");
  if (!parts.length && changes.analysis_updated)
    parts.push("Análisis actualizado");
  return parts.join(" · ") || "Página actualizada";
}
export function friendlyIssue(code: string) {
  if (code.startsWith("MODEL_"))
    return "El modelo no terminó de preparar este cambio. Puedes reintentarlo; el informe disponible se conserva.";
  if (/TIMEOUT|DEADLINE/.test(code))
    return "La preparación tardó más de lo previsto. Puedes volver a intentarlo; el informe disponible se conserva.";
  if (/UNAUTHORIZED|SESSION_EXPIRED/.test(code))
    return "Tu sesión ha caducado. Vuelve a entrar para continuar.";
  if (/RATE|BUSY|CAPACITY/.test(code))
    return "Hay varias consultas en curso. Espera un momento y vuelve a intentarlo.";
  if (/EVIDENCE|CATALOG/.test(code))
    return "No pude recuperar la información necesaria. Revisa el partido o vuelve a intentarlo.";
  return "La solicitud no se completó. Puedes reintentarlo o precisar lo que necesitas.";
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
