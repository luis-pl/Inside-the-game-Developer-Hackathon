import type { Lab } from "../hooks/use-lab.ts";
import type { PitchView } from "./PitchLegend.tsx";
export function ReadingGuide({
  lab,
  view,
  selectedOpening,
}: {
  lab: Lab;
  view: PitchView;
  selectedOpening: string | null;
}) {
  const { analysis, frame, episode } = lab;
  if (!analysis || !frame || !episode) return null;
  let title = "",
    description = "";
  if (view === "openings") {
    const opening =
      analysis.openings.find((o) => o.id === selectedOpening) ??
      analysis.openings[0];
    title = opening
      ? `${analysis.openings.length} ${analysis.openings.length === 1 ? "apertura destacada" : "aperturas destacadas"} entre defensores`
      : "Sin aperturas interiores destacadas";
    description = opening
      ? `${opening.id} permite un círculo libre de ${opening.diameter.toFixed(1)} m de diámetro. `
      : "Prueba otro instante o reduce la cobertura para explorar el modelo. ";
    description += !frame.ball
      ? "Falta la posición del balón para comprobar el acceso."
      : analysis.free.startCovered
        ? "El balón está dentro de una zona de cobertura: espacio libre no significa acceso inmediato."
        : analysis.free.reachable
          ? "Además, existe un camino libre desde el balón hasta el objetivo amarillo."
          : "El balón no está conectado al objetivo con el radio elegido.";
  } else if (view === "block") {
    title =
      analysis.h0 === 1
        ? "El equipo forma un solo grupo conectado"
        : `El equipo está separado en ${analysis.h0} grupos`;
    description = `Las líneas unen jugadores a ${lab.epsilon} m o menos. Los bordes del mismo color identifican un grupo. Eso describe cercanía, no calidad defensiva.`;
  } else {
    title = "Las flechas explican la circulación del balón";
    description =
      "Representan la componente seleccionada de los pases de toda la ventana. La punta marca su dirección; el grosor, su magnitud relativa. No son pases que estén ocurriendo en este segundo.";
  }
  return (
    <div
      className={`reading-guide ${analysis.free.reachable ? "connected" : ""}`}
      aria-live={lab.playing ? "off" : "polite"}
    >
      <span className="reading-icon">
        {view === "openings" ? "◎" : view === "block" ? "⦿" : "↗"}
      </span>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
        {lab.removed !== null && (
          <small>
            Comparación matemática activa: retiraste un jugador del modelo.
          </small>
        )}
      </div>
    </div>
  );
}
