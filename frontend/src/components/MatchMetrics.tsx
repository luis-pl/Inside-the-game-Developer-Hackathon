import type { Lab } from "../hooks/use-lab.ts";
import { connectionView } from "../domain/connection-view.ts";

export function MatchMetrics({ lab }: { lab: Lab }) {
  const { tactics, frame, episode } = lab;
  const connections = tactics && frame ? connectionView(tactics, frame) : null;
  const path = tactics?.featured?.path ?? tactics?.receiver?.path;
  const metrics = [
    {
      label: "Highlighted space",
      value: tactics?.featured?.diameter.toFixed(1) ?? "—",
      unit: "m",
      note: "Diameter · prioritises connected spaces",
      icon: "◎",
    },
    {
      label: "Connected attackers",
      value:
        frame?.ball && connections
          ? `${connections.connected}/${connections.total}`
          : "—",
      unit: "",
      note: frame?.ball
        ? `${connections?.direct ?? 0} directly connected to the ball`
        : "Ball position required",
      icon: "⌘",
    },
    {
      label: "Clear corridor",
      value: path && frame?.ball ? (2 * path.clearance).toFixed(1) : "—",
      unit: "m",
      note: "Narrowest width along the selected chain",
      icon: "↗",
    },
    {
      label: "Network groups",
      value:
        tactics && frame?.ball && frame.players.length >= 3
          ? String(tactics.network.components)
          : "—",
      unit: "",
      note: "Connected components · ball & attackers",
      icon: "◌",
    },
  ];
  return (
    <div className="analyst-metrics" aria-label="Current frame metrics">
      {metrics.map((metric, i) => (
        <article className={`analyst-metric metric-${i}`} key={metric.label}>
          <div>
            <span>{metric.label}</span>
            <i aria-hidden="true">{metric.icon}</i>
          </div>
          <strong>
            {episode ? metric.value : "—"}
            {episode && metric.value !== "—" && <small>{metric.unit}</small>}
          </strong>
          <p>{episode ? metric.note : "Load a match to see this metric"}</p>
        </article>
      ))}
    </div>
  );
}
