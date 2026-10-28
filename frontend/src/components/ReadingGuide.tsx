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
      ? `${analysis.openings.length} ${analysis.openings.length === 1 ? "highlighted space" : "highlighted spaces"} between defenders`
      : "No highlighted interior spaces";
    description = opening
      ? `${opening.id} contains an empty circle of ${opening.diameter.toFixed(1)} m in diameter. `
      : "Try another instant or reduce coverage to explore the model. ";
    description += !frame.ball
      ? "Ball position is needed to check access."
      : analysis.free.startCovered
        ? "The ball is inside a coverage zone: open space does not imply immediate access."
        : analysis.free.reachable
          ? "A clear path also connects the ball to the yellow target."
          : "The ball is not connected to the target at the selected radius.";
  } else if (view === "block") {
    title =
      analysis.h0 === 1
        ? "The team forms one connected group"
        : `The team is separated into ${analysis.h0} groups`;
    description = `Lines connect players within ${lab.epsilon} m. Matching outlines identify a group. This describes proximity, not defensive quality.`;
  } else {
    title = "Arrows show passing circulation";
    description =
      "They represent the selected passing component over the entire window. Arrowheads indicate direction; thickness indicates relative magnitude. These are not passes occurring at this instant.";
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
            Geometric comparison active: a player has been removed from the
            model.
          </small>
        )}
      </div>
    </div>
  );
}
