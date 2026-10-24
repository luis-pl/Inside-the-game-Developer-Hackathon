import { useId } from "react";
import type { Frame } from "../domain/types.ts";
import type { Analysis } from "../domain/analysis.ts";
import { HodgeOverlay } from "./HodgeOverlay.tsx";
import { OpeningOverlay } from "./OpeningOverlay.tsx";
import { LiveOverlay } from "./LiveOverlay.tsx";
import { AttackingConnections } from "./AttackingConnections.tsx";
import type { Tactics } from "../domain/tactics.ts";
import type { PitchView } from "./PitchLegend.tsx";
import type {
  HodgeAnalysis,
  HodgeComponent,
} from "../domain/hodge/decomposition.ts";

const COLORS = [
  "#91dcc4",
  "#b5b0fc",
  "#f3ce83",
  "#ed9cba",
  "#a6d6ff",
  "#dce89b",
  "#efa183",
  "#ffffff",
  "#abc4b0",
  "#d7badc",
];
interface Props {
  tactics?: Tactics;
  broadcast?: boolean;
  mintTeamId?: number;
  frame: Frame;
  analysis: Analysis;
  teamId: number;
  removed: number | null;
  radius: number;
  coverage: boolean;
  spaces: boolean;
  connections: boolean;
  route: boolean;
  attackRight: boolean;
  onRemove: (id: number | null) => void;
  hodge: HodgeAnalysis | null;
  hodgeLayer: HodgeComponent | "off";
  showOpenings: boolean;
  selectedOpening: string | null;
  view: PitchView;
}

export function Pitch(p: Props) {
  const clip = useId();
  const groupColor = (id: number) =>
    COLORS[
      Math.max(
        0,
        p.analysis.graph.groups.findIndex((g) => g.includes(id)),
      ) % COLORS.length
    ];
  return (
    <svg
      className="pitch-svg"
      viewBox={p.broadcast ? "-3 -4 111 76" : "-5 -7 115 82"}
      role="group"
      aria-label="Cancha de fútbol: jugadores, cobertura y espacio libre"
    >
      <defs>
        <clipPath id={clip}>
          <rect width="105" height="68" />
        </clipPath>
      </defs>
      <rect x="-5" y="-7" width="115" height="82" fill="#102a24" />
      {Array.from({ length: 10 }, (_, i) => (
        <rect
          key={i}
          x={i * 10.5}
          width="10.5"
          height="68"
          fill={i % 2 ? "#173c31" : "#14372e"}
        />
      ))}
      <g clipPath={`url(#${clip})`}>
        {!p.broadcast && (
          <rect
            x={p.attackRight ? 100 : 0}
            y="24"
            width="5"
            height="20"
            fill="#f2cd68"
            fillOpacity=".22"
            stroke="#f2cd68"
            strokeWidth=".25"
            strokeDasharray="1 .7"
          />
        )}
        {p.spaces &&
          p.analysis.free.runs.map((r, i) => (
            <rect
              key={i}
              x={r.x}
              y={r.y}
              width={r.width}
              height="1"
              fill={COLORS[r.label % COLORS.length]}
              opacity="0.12"
            />
          ))}
        {p.coverage &&
          p.frame.players
            .filter((v) => v.teamId === p.teamId && v.id !== p.removed)
            .map((v) => (
              <circle
                key={v.id}
                cx={v.x}
                cy={v.y}
                r={p.radius}
                fill="#84dec0"
                fillOpacity=".045"
                stroke="#8de5c5"
                strokeWidth=".18"
                strokeDasharray=".6 .5"
              />
            ))}
      </g>
      {p.showOpenings && (
        <g clipPath={`url(#${clip})`}>
          <OpeningOverlay
            openings={p.analysis.openings}
            selected={p.selectedOpening}
          />
        </g>
      )}
      {p.broadcast && p.view === "openings" && p.tactics && (
        <LiveOverlay
          tactics={p.tactics}
          attackRight={p.attackRight}
          frame={p.frame}
        />
      )}
      <g fill="none" stroke="#b7cfbd" strokeOpacity=".52" strokeWidth=".18">
        <rect width="105" height="68" />
        <path d="M52.5 0V68" />
        <circle cx="52.5" cy="34" r="9.15" />
        <path d="M0 13.84H16.5V54.16H0 M105 13.84H88.5V54.16H105 M0 24.84H5.5V43.16H0 M105 24.84H99.5V43.16H105" />
        <path d="M16.5 26.7A9.15 9.15 0 0 1 16.5 41.3 M88.5 26.7A9.15 9.15 0 0 0 88.5 41.3" />
        <circle cx="11" cy="34" r=".25" fill="#b7cfbd" />
        <circle cx="94" cy="34" r=".25" fill="#b7cfbd" />
        <path d="M0 30H-1.8V38H0 M105 30H106.8V38H105" />
      </g>
      {p.broadcast && p.tactics && p.view !== "passing" && (
        <AttackingConnections
          frame={p.frame}
          tactics={p.tactics}
          full={p.view === "block"}
        />
      )}
      {p.connections &&
        !p.broadcast &&
        p.tactics &&
        p.tactics.network.edges.map((edge) => (
          <line
            key={`${edge.a.id}-${edge.b.id}`}
            x1={edge.a.x}
            y1={edge.a.y}
            x2={edge.b.x}
            y2={edge.b.y}
            stroke="#caff7a"
            strokeWidth=".3"
            opacity=".8"
          />
        ))}
      {p.connections &&
        !p.tactics &&
        p.analysis.graph.edges.map(({ a, b }) => (
          <line
            key={`${a.id}-${b.id}`}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={groupColor(a.id)}
            strokeWidth=".32"
            opacity=".65"
          />
        ))}
      {p.route && p.analysis.free.route.length > 0 && (
        <polyline
          points={p.analysis.free.route.map((v) => `${v.x},${v.y}`).join(" ")}
          fill="none"
          stroke="#e6f5a2"
          strokeWidth=".65"
          strokeDasharray="1 .7"
        />
      )}
      {p.hodge?.reliable && p.hodgeLayer !== "off" && (
        <HodgeOverlay
          frame={p.frame}
          analysis={p.hodge}
          component={p.hodgeLayer}
        />
      )}
      {p.frame.players.map((v) => {
        const defender = v.teamId === p.teamId,
          excluded = v.id === p.removed;
        return (
          <g
            key={v.id}
            role={
              !p.broadcast && defender && !v.goalkeeper ? "button" : undefined
            }
            tabIndex={!p.broadcast && defender && !v.goalkeeper ? 0 : undefined}
            aria-label={`${v.name}, dorsal ${v.number}${!p.broadcast && defender && !v.goalkeeper ? ", " + (excluded ? "restaurar" : "retirar del modelo") : ""}`}
            onClick={() => {
              if (!p.broadcast && defender && !v.goalkeeper)
                p.onRemove(excluded ? null : v.id);
            }}
            onKeyDown={(e) => {
              if (
                !p.broadcast &&
                defender &&
                !v.goalkeeper &&
                (e.key === "Enter" || e.key === " ")
              ) {
                e.preventDefault();
                p.onRemove(excluded ? null : v.id);
              }
            }}
            className={
              !p.broadcast && defender && !v.goalkeeper
                ? "player selectable"
                : "player"
            }
          >
            <title>
              {v.name}
              {v.goalkeeper ? " · portero" : ""}
            </title>
            <circle
              cx={v.x}
              cy={v.y}
              r="1.8"
              fill={
                excluded
                  ? "#17382f"
                  : v.teamId === (p.mintTeamId ?? p.teamId)
                    ? "#91dcc4"
                    : "#e6b779"
              }
              stroke={
                excluded
                  ? "#f4f3e9"
                  : !p.broadcast &&
                      defender &&
                      !v.goalkeeper &&
                      p.view === "block"
                    ? groupColor(v.id)
                    : "#102b23"
              }
              strokeWidth={defender && p.view === "block" ? ".65" : ".35"}
              strokeDasharray={excluded ? ".5 .4" : undefined}
            />
            <text
              x={v.x}
              y={v.y + 0.53}
              textAnchor="middle"
              fontSize="1.55"
              fontWeight="800"
              fill={excluded ? "#fff" : "#102b23"}
            >
              {excluded ? "×" : v.number}
            </text>
            {!p.broadcast &&
              defender &&
              !v.goalkeeper &&
              !excluded &&
              p.view === "block" && (
                <text
                  x={v.x}
                  y={v.y + 3.3}
                  textAnchor="middle"
                  fontSize="1.1"
                  fontWeight="700"
                  fill="#e6f5dc"
                >
                  G
                  {p.analysis.graph.groups.findIndex((g) => g.includes(v.id)) +
                    1}
                </text>
              )}
          </g>
        );
      })}
      {p.frame.ball && (
        <g>
          <circle
            cx={p.frame.ball.x}
            cy={p.frame.ball.y}
            r=".85"
            fill="#fff"
            stroke="#102b23"
            strokeWidth=".3"
          />
          <circle
            cx={p.frame.ball.x}
            cy={p.frame.ball.y}
            r=".22"
            fill="#102b23"
          />
          <circle
            cx={p.frame.ball.x}
            cy={p.frame.ball.y}
            r="1.5"
            fill="none"
            stroke="#fff"
            strokeWidth=".18"
          />
          <text
            x={p.frame.ball.x}
            y={p.frame.ball.y - 2.1}
            fill="#fff"
            textAnchor="middle"
            fontSize="1.1"
            fontWeight="700"
          >
            BALÓN
          </text>
        </g>
      )}
      {!p.broadcast && (
        <text x="0" y="-3" className="pitch-label">
          105 × 68 M · COORDENADAS EN METROS
        </text>
      )}
      {!p.broadcast && (
        <text x="105" y="73" textAnchor="end" className="pitch-label">
          ZONA OBJETIVO EN AMARILLO {p.attackRight ? "→" : "←"}
        </text>
      )}
    </svg>
  );
}
