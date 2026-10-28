import type { Tactics } from "../domain/tactics.ts";
import type { Frame } from "../domain/types.ts";
import { projectNode } from "../domain/connection-view.ts";

export function LiveOverlay({
  tactics,
  attackRight,
  frame,
}: {
  tactics: Tactics;
  attackRight: boolean;
  frame: Frame;
}) {
  const opening = tactics.featured;
  const path = opening?.path ?? tactics.receiver?.path;
  const projected = path?.nodes.map((node) => projectNode(node, frame));
  const pathNodes = projected?.every((node) => node !== null)
    ? projected
    : null;
  return (
    <g className="live-overlay" pointerEvents="none">
      {opening && (
        <g>
          <circle
            cx={opening.center.x}
            cy={opening.center.y}
            r={opening.radius}
            fill="#ffdb63"
            fillOpacity=".07"
            stroke="#ffe58c"
            strokeWidth=".35"
          />
        </g>
      )}
      {pathNodes && (
        <>
          <polyline
            points={pathNodes.map((n) => `${n.x},${n.y}`).join(" ")}
            fill="none"
            stroke="#152e24"
            strokeWidth="1.05"
          />
          <polyline
            points={pathNodes.map((n) => `${n.x},${n.y}`).join(" ")}
            fill="none"
            stroke="#ffe58c"
            strokeWidth=".48"
            strokeDasharray="1.4 .8"
            strokeLinejoin="round"
          />
        </>
      )}
      <text
        x={attackRight ? 103 : 2}
        y="-2.8"
        textAnchor={attackRight ? "end" : "start"}
        fill="#d4e8ce"
        fontSize="1.3"
        fontWeight="700"
      >
        {attackRight ? "ATTACK →" : "← ATTACK"}
      </text>
    </g>
  );
}
