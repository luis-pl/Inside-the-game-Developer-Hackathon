import type { Frame } from "../domain/types.ts";
import type { Tactics } from "../domain/tactics.ts";
import { connectionView } from "../domain/connection-view.ts";

export function AttackingConnections({
  frame,
  tactics,
  full = false,
}: {
  frame: Frame;
  tactics: Tactics;
  full?: boolean;
}) {
  const view = connectionView(tactics, frame);
  return (
    <g
      className="attacking-connections"
      pointerEvents="none"
      aria-label="Conexiones de los atacantes"
    >
      {view.edges.map((edge) => (
        <line
          key={`${edge.a.id}-${edge.b.id}`}
          data-connection={edge.kind}
          x1={edge.a.x}
          y1={edge.a.y}
          x2={edge.b.x}
          y2={edge.b.y}
          stroke={edge.kind === "separate" ? "#c6d7cd" : "#b6ff75"}
          strokeWidth={
            edge.kind === "direct" ? 0.55 : edge.kind === "relay" ? 0.36 : 0.2
          }
          opacity={edge.kind === "separate" ? (full ? 0.6 : 0.3) : 0.95}
          strokeDasharray={edge.kind === "separate" ? ".45 .65" : undefined}
        >
          <title>
            {edge.kind === "separate"
              ? "Conexión entre atacantes sin enlace al balón"
              : edge.kind === "direct"
                ? "Conexión directa desde el balón"
                : "Conexión a través de compañeros"}{" "}
            · corredor {(2 * edge.clearance).toFixed(1)} m
          </title>
        </line>
      ))}
      {view.nodes.map(({ player, kind }) => (
        <circle
          key={player.id}
          data-attacker-node={kind}
          cx={player.x}
          cy={player.y}
          r={kind === "direct" ? 2.6 : 2.35}
          fill="none"
          stroke={
            kind === "separate"
              ? "#c6d7cd"
              : kind === "source"
                ? "#fff"
                : "#b6ff75"
          }
          strokeWidth={kind === "direct" ? 0.5 : 0.3}
          strokeDasharray={kind === "separate" ? ".35 .55" : undefined}
          opacity={kind === "separate" ? 0.65 : 1}
        >
          <title>
            #{player.number}:{" "}
            {kind === "separate"
              ? "sin conexión al balón en esta red"
              : kind === "direct"
                ? "enlace directo al balón"
                : kind === "source"
                  ? "coincide con el balón"
                  : "enlazado a través de compañeros"}
          </title>
        </circle>
      ))}
    </g>
  );
}
