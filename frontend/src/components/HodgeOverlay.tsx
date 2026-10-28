import { useId } from "react";
import type { Frame } from "../domain/types.ts";
import type {
  HodgeAnalysis,
  HodgeComponent,
} from "../domain/hodge/decomposition.ts";

export const HODGE_COLORS = {
  net: "#f8f2da",
  gradient: "#8fe0d0",
  curl: "#f2ca80",
  harmonic: "#bdb0fa",
};
export function HodgeOverlay({
  frame,
  analysis,
  component,
}: {
  frame: Frame;
  analysis: HodgeAnalysis;
  component: HodgeComponent;
}) {
  const marker = useId();
  const values = component === "net" ? analysis.flow : analysis[component];
  const largest = Math.max(...values.map(Math.abs), 1e-9);
  const positions = new Map(frame.players.map((p) => [p.id, p]));
  return (
    <g className="hodge-overlay" aria-label={`Hodge flow: ${component}`}>
      <defs>
        <marker
          id={marker}
          markerWidth="4"
          markerHeight="4"
          refX="3.5"
          refY="2"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0 0L4 2L0 4Z" fill={HODGE_COLORS[component]} />
        </marker>
      </defs>
      {analysis.edges.map((edge, i) => {
        const value = values[i];
        const a = positions.get(value >= 0 ? edge.source : edge.target),
          b = positions.get(value >= 0 ? edge.target : edge.source);
        if (!a || !b || Math.abs(value) < 1e-8) return null;
        const dx = b.x - a.x,
          dy = b.y - a.y,
          length = Math.hypot(dx, dy);
        if (length < 4) return null;
        return (
          <line
            key={`${edge.source}-${edge.target}`}
            x1={a.x + (dx / length) * 1.8}
            y1={a.y + (dy / length) * 1.8}
            x2={b.x - (dx / length) * 2.1}
            y2={b.y - (dy / length) * 2.1}
            stroke={HODGE_COLORS[component]}
            strokeWidth={0.22 + (0.55 * Math.abs(value)) / largest}
            markerEnd={`url(#${marker})`}
            opacity=".95"
          >
            <title>
              {a.name} → {b.name}: {Math.abs(value).toFixed(3)} flow units
            </title>
          </line>
        );
      })}
    </g>
  );
}
