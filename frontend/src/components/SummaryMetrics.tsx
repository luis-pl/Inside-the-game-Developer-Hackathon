import type { Lab } from "../hooks/use-lab.ts";

export function SummaryMetrics({ lab }: { lab: Lab }) {
  const { analysis, frame } = lab;
  const noPath = analysis?.free.startCovered
    ? "Balón dentro de cobertura"
    : frame?.ball
      ? "Sin camino en esta malla"
      : "Sin posición de balón";
  return (
    <div className="metric-row">
      <Metric
        label="GRUPOS DEL EQUIPO"
        value={analysis ? String(analysis.h0) : "—"}
        note={
          analysis
            ? `${analysis.baseline.groups.length} antes de retirar`
            : "Conectividad del bloque"
        }
      />
      <Metric
        label="APERTURAS DESTACADAS"
        value={analysis ? String(analysis.openings.length) : "—"}
        note="Espacios interiores · hasta 3"
      />
      <Metric
        label="MAYOR APERTURA"
        value={
          analysis?.openings[0]
            ? `${analysis.openings[0].diameter.toFixed(1)} m`
            : "—"
        }
        note="Diámetro del círculo libre"
      />
      <Metric
        label="CAMINO AL OBJETIVO"
        value={
          analysis
            ? analysis.free.reachable
              ? "Hay camino"
              : "Sin camino"
            : "—"
        }
        note={
          analysis
            ? analysis.free.reachable
              ? "Bajo el radio elegido"
              : noPath
            : "Desde el balón"
        }
        compact
      />
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  compact = false,
}: {
  label: string;
  value: string;
  note: string;
  compact?: boolean;
}) {
  return (
    <article className="metric panel">
      <span>{label}</span>
      <strong className={compact ? "compact" : ""}>{value}</strong>
      <small>{note}</small>
    </article>
  );
}
