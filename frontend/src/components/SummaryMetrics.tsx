import type { Lab } from "../hooks/use-lab.ts";

export function SummaryMetrics({ lab }: { lab: Lab }) {
  const { analysis, frame } = lab;
  const noPath = analysis?.free.startCovered
    ? "Ball inside coverage"
    : frame?.ball
      ? "No path in this grid"
      : "Ball position unavailable";
  return (
    <div className="metric-row">
      <Metric
        label="TEAM GROUPS"
        value={analysis ? String(analysis.h0) : "—"}
        note={
          analysis
            ? `${analysis.baseline.groups.length} before removal`
            : "Block connectivity"
        }
      />
      <Metric
        label="HIGHLIGHTED SPACES"
        value={analysis ? String(analysis.openings.length) : "—"}
        note="Interior spaces · up to 3"
      />
      <Metric
        label="LARGEST SPACE"
        value={
          analysis?.openings[0]
            ? `${analysis.openings[0].diameter.toFixed(1)} m`
            : "—"
        }
        note="Diameter of the empty circle"
      />
      <Metric
        label="PATH TO TARGET"
        value={
          analysis ? (analysis.free.reachable ? "Connected" : "No path") : "—"
        }
        note={
          analysis
            ? analysis.free.reachable
              ? "At the selected radius"
              : noPath
            : "From the ball"
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
