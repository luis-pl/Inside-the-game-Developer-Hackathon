import type { Lab } from "../hooks/use-lab.ts";
import { useMemo } from "react";
import { episodeActions } from "../domain/playback.ts";
export const matchClock = (ms: number) =>
  `${String(Math.floor(ms / 60000)).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

export function MatchPlayback({ lab }: { lab: Lab }) {
  const actions = useMemo(() => episodeActions(lab.episode), [lab.episode]);
  const next =
    actions.find((action) => action.timeMs > lab.playheadMs + 2000) ??
    actions[0];
  const current = actions.findLast((action) => action.timeMs <= lab.playheadMs);
  const passCount =
    lab.episode?.events.filter((e) => e.label === "Pass").length ?? 0;
  const shotCount =
    lab.episode?.events.filter((e) => e.label === "Shot").length ?? 0;
  return (
    <>
      <div className="match-playback">
        <button
          className="match-play"
          disabled={!lab.episode || lab.loading}
          aria-label={lab.playing ? "Pausar partido" : "Reproducir partido"}
          onClick={() => {
            if (lab.episode && lab.index === lab.episode.frames.length - 1)
              lab.setIndex(0);
            lab.setPlaying(!lab.playing);
          }}
        >
          {lab.playing ? "Ⅱ" : "▶"}
        </button>
        <input
          type="range"
          aria-label="Momento del partido"
          min={lab.episode?.frames[0].timeMs ?? 0}
          max={lab.episode?.frames.at(-1)!.timeMs ?? 1}
          step="any"
          value={lab.playheadMs}
          disabled={!lab.episode}
          onChange={(e) => {
            lab.setPlaying(false);
            lab.seekTime(Number(e.target.value));
          }}
        />
        <span>
          {lab.episode
            ? matchClock(lab.episode.frames.at(-1)!.timeMs)
            : "00:00"}
        </span>
        <select
          aria-label="Velocidad del partido"
          title="1× = tiempo real: un segundo de partido por segundo de pantalla"
          value={lab.speed}
          onChange={(e) => lab.setSpeed(Number(e.target.value))}
        >
          <option value="0.5">0.5×</option>
          <option value="1">1×</option>
          <option value="2">2×</option>
          <option value="4">4×</option>
          <option value="8">8×</option>
        </select>
        <button
          className="next-action"
          disabled={!next}
          onClick={() => {
            if (next) {
              lab.seekTime(
                Math.max(lab.episode!.frames[0].timeMs, next.timeMs - 2000),
              );
              lab.setPlaying(true);
            }
          }}
        >
          Próxima acción ▷
        </button>
      </div>
      {lab.episode && (
        <div className="match-action-strip">
          <span>
            {lab.episode.events.length.toLocaleString("es")} acciones ·{" "}
            {passCount} pases · {shotCount} tiros
          </span>
          <strong>
            {current
              ? `${matchClock(current.timeMs)} · ${current.displayLabel}`
              : "Inicio de la secuencia"}
          </strong>
        </div>
      )}
    </>
  );
}
