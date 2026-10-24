import type { Bar } from "../domain/types.ts";

export function Persistence({
  bars,
  epsilon,
}: {
  bars: Bar[];
  epsilon?: number;
}) {
  const visible = bars.filter((b) => b.dimension === 1);
  return (
    <div className="persistence-chart">
      <div className="scale">
        <span>0 m</span>
        <span>20</span>
        <span>40 m</span>
      </div>
      <div className="bars" aria-label="Intervalos de persistencia H1">
        {epsilon !== undefined && (
          <div
            className="scale-marker"
            style={{ left: `${(epsilon / 40) * 100}%` }}
          />
        )}
        {visible.length ? (
          visible.map((bar, i) => (
            <div key={i} className="bar-row">
              <div
                className="bar"
                title={`Nacimiento ${bar.birth.toFixed(2)} m; ${bar.death === null ? "censurado a 40 m" : "muerte " + bar.death.toFixed(2) + " m"}`}
                style={{
                  left: `${(bar.birth / 40) * 100}%`,
                  width: `${(((bar.death ?? 40) - bar.birth) / 40) * 100}%`,
                }}
              >
                {bar.death === null ? "→" : ""}
              </div>
            </div>
          ))
        ) : (
          <p className="muted small">
            No hay ciclos H₁ con persistencia positiva en este frame.
          </p>
        )}
      </div>
      <p className="small muted">
        Rips · F₂ · corte a 40 m. Persistencia en distancia, no duración
        temporal. Un ciclo no delimita por sí solo un hueco táctico.
      </p>
    </div>
  );
}
