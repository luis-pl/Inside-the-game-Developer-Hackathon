import type { Lab } from "../hooks/use-lab.ts";
import { Persistence } from "./Persistence.tsx";
export function Insights({ lab }: { lab: Lab }) {
  const { analysis, frame } = lab;
  const selected = frame?.players.find((p) => p.id === lab.removed);
  return (
    <aside className="insights-column">
      <section className="panel insight">
        <div className="section-label">03 / LA FORMA QUE PERMANECE</div>
        <h2>Más allá de las distancias.</h2>
        <p className="muted small">Intervalos H₁ del equipo seleccionado.</p>
        {analysis ? (
          <Persistence bars={analysis.bars} epsilon={lab.epsilon} />
        ) : (
          <p className="placeholder-text">
            Al cargar una ventana, aquí verás la firma topológica del bloque.
          </p>
        )}
        <div className="legend-line">
          <i /> Ciclo H₁ <span>| ε actual</span>
        </div>
      </section>
      <section className="panel insight">
        <div className="section-label">04 / PRUEBA DE ESTRUCTURA</div>
        <h2>¿Quién mantiene unido al equipo?</h2>
        <p className="muted small">
          Retira un jugador del grafo y compara su conectividad.
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
              Restaurar jugador ↺
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
                  <small>{components} componentes sin este nodo</small>
                </span>
                <strong>
                  {delta > 0 ? "+" : ""}
                  {delta}
                </strong>
              </button>
            )) ?? (
            <p className="placeholder-text">
              Una perturbación pequeña puede cambiar toda la conexión.
            </p>
          )}
        </div>
        <p className="small muted">
          Ranking de Δ componentes. Retirada estática, sin simular el movimiento
          del resto.
        </p>
      </section>
      <div className="editorial-note">
        <span>TOPOLOGÍA, CON CONTEXTO.</span>
        <p>
          Un espacio abierto no siempre es una oportunidad. El balón, la
          dirección y la escala importan.
        </p>
      </div>
    </aside>
  );
}
