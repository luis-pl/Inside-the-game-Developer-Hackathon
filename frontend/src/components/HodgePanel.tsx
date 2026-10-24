import type { Lab } from "../hooks/use-lab.ts";
import type { HodgeComponent } from "../domain/hodge/decomposition.ts";
import { HODGE_COLORS } from "./HodgeOverlay.tsx";
import "./hodge.css";

const PARTS = [
  {
    key: "gradient",
    name: "Potencial",
    description: "Flujo de gradiente; no equivale a avance hacia portería.",
  },
  {
    key: "curl",
    name: "Circulación local",
    description: "Combinación de fronteras de los triángulos rellenos.",
  },
  {
    key: "harmonic",
    name: "Armónico",
    description:
      "Flujo sin divergencia ni rotación local; depende del complejo.",
  },
] as const;
const percent = (value: number | null) =>
  value === null ? "—" : `${(value * 100).toFixed(1)} %`;

export function HodgePanel({ lab }: { lab: Lab }) {
  const h = lab.hodge,
    frame = lab.frame;
  const missing =
    h?.nodes.filter((id) => !frame?.players.some((p) => p.id === id)).length ??
    0;
  return (
    <section className="panel hodge-panel">
      <div className="hodge-header">
        <div>
          <div className="section-label">05 / ANATOMÍA DE LA CIRCULACIÓN</div>
          <h2>El balón también tiene estructura.</h2>
        </div>
        <label>
          Complejo de pases
          <select
            aria-label="Complejo de pases"
            value={lab.complexMode}
            onChange={(e) =>
              lab.setComplexMode(e.target.value as "clique" | "graph")
            }
          >
            <option value="clique">Triángulos rellenos</option>
            <option value="graph">Sólo grafo</option>
          </select>
        </label>
      </div>
      {!lab.episode ? (
        <p className="muted small">
          Carga un episodio para descomponer la red de pases completados.
        </p>
      ) : !h ? (
        <p className="notice error" role="status">
          Hodge no disponible: faltan datos completos de pases. No se interpreta
          como cero circulación.
        </p>
      ) : (
        <>
          <p className="small muted">
            Red agregada de toda la ventana cargada (
            {Math.round(
              (lab.episode.frames.at(-1)!.timeMs -
                lab.episode.frames[0].timeMs +
                1000) /
                1000,
            )}{" "}
            s), no del instante.{" "}
            {lab.removed !== null
              ? "Red perturbada: se excluyen los pases del jugador retirado."
              : "Incluye porteros si participaron en los pases."}
          </p>
          <div className="hodge-facts">
            <span>
              <strong>{h.completedCount}</strong> pases completos
            </span>
            <span>
              <strong>{h.edges.length}</strong> interacciones
            </span>
            <span>
              <strong>{h.triangles.length}</strong> triángulos
            </span>
            <span>
              <strong>{h.firstBetti}</strong> dimensión H¹(ℝ)
            </span>
          </div>
          <div className="hodge-parts">
            {PARTS.map((part) => (
              <article
                key={part.key}
                style={{ borderTopColor: HODGE_COLORS[part.key] }}
              >
                <span>{part.name}</span>
                <strong>{percent(h.fractions?.[part.key] ?? null)}</strong>
                <p>{part.description}</p>
              </article>
            ))}
          </div>
          <p className="small muted">
            Porcentajes de energía ‖componente‖² / ‖flujo neto‖². No son
            porcentajes de posesión ni de eficacia.
          </p>
          {!h.fractions && (
            <div className="notice">
              {h.completedCount
                ? "Los pases en ambos sentidos se equilibran: el flujo neto es nulo."
                : "No hay pases completados atribuibles a este equipo en esta ventana."}{" "}
              No se calculan porcentajes.
            </div>
          )}
          <div
            className="hodge-layer-buttons"
            aria-label="Capa de Hodge sobre la cancha"
          >
            <span>VER EN CANCHA</span>
            {(
              [
                { key: "off", name: "Oculto" },
                { key: "net", name: "Flujo neto" },
                ...PARTS,
              ] as const
            ).map((part) => (
              <button
                key={part.key}
                type="button"
                aria-pressed={lab.hodgeLayer === part.key}
                onClick={() =>
                  lab.setHodgeLayer(part.key as HodgeComponent | "off")
                }
              >
                {part.name}
              </button>
            ))}
          </div>
          {missing > 0 && (
            <p className="small muted">
              {missing} nodos de la red no están presentes en este frame. Sus
              aristas se incluyen en el cálculo, pero no se dibujan con
              posiciones inventadas.
            </p>
          )}
          <details className="hodge-method">
            <summary>Definición y control numérico</summary>
            <p>
              Orientación canónica por ID: fᵢⱼ = Nᵢ→ⱼ − Nⱼ→ᵢ. Producto interno
              euclídeo sin pesos. f = B₁ᵀφ + B₂ψ + h. El soporte conserva pares
              con pases equilibrados; cada triángulo exige las tres
              interacciones observadas, sin afirmar que ocurrieran en secuencia.
            </p>
            <p>
              La componente armónica satisface B₁h = 0 y B₂ᵀh = 0. Su espacio
              representa H¹ con coeficientes reales del complejo de pases; es
              distinto del H₁ de Rips espacial sobre F₂. No se equipara
              gradiente con progresión ni circulación con posesión improductiva.
            </p>
            <p>
              Residuos relativos: reconstrucción{" "}
              {h.diagnostics.reconstruction.toExponential(1)}, divergencia
              armónica {h.diagnostics.harmonicDivergence.toExponential(1)},
              rotación armónica {h.diagnostics.harmonicCurl.toExponential(1)},
              ortogonalidad {h.diagnostics.orthogonality.toExponential(1)}.
            </p>
          </details>
          {!h.reliable && (
            <p role="alert" className="notice error">
              Los residuos numéricos superan la tolerancia. No se dibuja esta
              descomposición.
            </p>
          )}
        </>
      )}
    </section>
  );
}
