import type { Lab } from "../hooks/use-lab.ts";
import { Persistence } from "./Persistence.tsx";
export function Insights({ lab }: { lab: Lab }) {
  const { analysis, frame } = lab;
  const selected = frame?.players.find((p) => p.id === lab.removed);
  return (
    <aside className="insights-column">
      <section className="panel insight">
        <div className="section-label">03 / PERSISTENT STRUCTURE</div>
        <h2>Beyond player distances.</h2>
        <p className="muted small">H₁ intervals for the selected team.</p>
        {analysis ? (
          <Persistence bars={analysis.bars} epsilon={lab.epsilon} />
        ) : (
          <p className="placeholder-text">
            Load a match window to see the block's topological signature.
          </p>
        )}
        <div className="legend-line">
          <i /> H₁ cycle <span>| current ε</span>
        </div>
      </section>
      <section className="panel insight">
        <div className="section-label">04 / STRUCTURAL TEST</div>
        <h2>Who connects the team?</h2>
        <p className="muted small">
          Remove a player from the graph and compare connectivity.
        </p>
        {selected && (
          <div className="removal-banner">
            <strong>
              #{selected.number} · {selected.name}
            </strong>
            <span>
              {analysis!.baseline.groups.length} →{" "}
              {analysis!.graph.groups.length} componentes
            </span>
            <button
              className="text-button"
              onClick={() => lab.setRemoved(null)}
            >
              Restore player ↺
            </button>
          </div>
        )}
        <div className="player-list">
          {analysis?.removal
            .slice(0, 5)
            .map(({ player, delta, components }) => (
              <button
                key={player.id}
                className={lab.removed === player.id ? "selected" : ""}
                onClick={() =>
                  lab.setRemoved(lab.removed === player.id ? null : player.id)
                }
              >
                <span className="jersey">{player.number}</span>
                <span className="player-name">
                  {player.name}
                  <small>{components} components without this node</small>
                </span>
                <strong>
                  {delta > 0 ? "+" : ""}
                  {delta}
                </strong>
              </button>
            )) ?? (
            <p className="placeholder-text">
              A small change can reshape connectivity.
            </p>
          )}
        </div>
        <p className="small muted">
          Ranked by change in components. Static removal; other players do not
          move.
        </p>
      </section>
      <div className="editorial-note">
        <span>TOPOLOGY IN CONTEXT.</span>
        <p>
          Open space is not always an opportunity. The ball, direction and scale
          matter.
        </p>
      </div>
    </aside>
  );
}
