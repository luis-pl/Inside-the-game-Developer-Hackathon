import { useMemo, useState } from "react";
const clock = (ms: number) =>
  `${String(Math.floor(ms / 60000)).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

import type { Lab } from "../hooks/use-lab.ts";
import { episodeTiming } from "../domain/playback.ts";

export function Timeline({ lab }: { lab: Lab }) {
  const { episode, frame } = lab;
  const [metric, setMetric] = useState<"openings" | "groups">("openings");
  const series = useMemo(
    () => lab.tacticalSeries.map((t) => t.network.components),
    [lab.tacticalSeries],
  );
  const values = metric === "openings" ? lab.openingSeries : series;
  const largest = Math.max(1, ...values);
  const jumpToOpening = () => {
    setMetric("openings");
    lab.goToOpening();
    document.getElementById("pitch-analysis")?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  };
  return (
    <section className="timeline panel">
      <div className="timeline-top">
        <div className="playback">
          <button
            className="play-button"
            aria-label={lab.playing ? "Pausar" : "Reproducir"}
            disabled={!episode || lab.loading}
            onClick={() => {
              if (episode && lab.index === episode.frames.length - 1)
                lab.setIndex(0);
              lab.setPlaying(!lab.playing);
            }}
          >
            {lab.playing ? "Ⅱ" : "▶"}
          </button>
          <strong>{frame ? clock(frame.timeMs) : "00:00"}</strong>
          <span>
            / {episode ? clock(episode.frames.at(-1)!.timeMs) : "00:00"}
          </span>
        </div>
        <label className="speed">
          Velocidad de reproducción
          <select
            aria-label="Velocidad de reproducción"
            value={lab.speed}
            onChange={(e) => lab.setSpeed(Number(e.target.value))}
          >
            <option value="0.5">0.5×</option>
            <option value="1">1×</option>
            <option value="2">2×</option>
            <option value="4">4×</option>
            <option value="8">8×</option>
          </select>
        </label>
      </div>
      <input
        className="scrubber"
        aria-label="Instante de la ventana"
        type="range"
        min={episode?.frames[0].timeMs ?? 0}
        max={episode?.frames.at(-1)!.timeMs ?? 1}
        step="any"
        value={lab.playheadMs}
        disabled={!episode}
        onChange={(e) => {
          lab.setPlaying(false);
          lab.seekTime(Number(e.target.value));
        }}
      />
      <div className="timeline-explorer">
        <div>
          <strong>
            {metric === "openings"
              ? "¿Cuándo se abre más el espacio?"
              : "¿Cuándo cambia la red?"}
          </strong>
          <p>
            {metric === "openings"
              ? "La altura de cada barra indica el tamaño de la apertura en ese instante."
              : "Componentes de la red geométrica de balón y atacantes."}
          </p>
        </div>
        <button
          className="button secondary"
          disabled={!episode || !lab.openingSeries.some((v) => v > 0)}
          onClick={jumpToOpening}
        >
          Ir a la mayor apertura ↗
        </button>
      </div>
      <div className="timeline-modes">
        <button
          aria-pressed={metric === "openings"}
          onClick={() => setMetric("openings")}
        >
          Tamaño de aperturas
        </button>
        <button
          aria-pressed={metric === "groups"}
          onClick={() => setMetric("groups")}
        >
          Componentes de la red
        </button>
      </div>
      <div
        className="sparkline"
        aria-label={
          metric === "openings"
            ? "Apertura mayor por muestra"
            : "Componentes por muestra"
        }
      >
        {values.map((n, i) => (
          <button
            key={i}
            aria-label={`Ir a ${clock(episode!.frames[i].timeMs)}, ${metric === "openings" ? n.toFixed(1) + " metros de apertura" : n + " grupos"}`}
            onClick={() => {
              lab.setPlaying(false);
              lab.setIndex(i);
            }}
            style={{ height: `${6 + (n / largest) * 34}px` }}
            className={i === lab.index ? "current" : ""}
          />
        ))}
      </div>
      <div className="timeline-caption">
        <span>
          {metric === "openings"
            ? "APERTURA MAYOR POR INSTANTE"
            : "GRUPOS SEPARADOS"}
        </span>
        <span>
          {metric === "openings" ? "Diámetro en metros" : "Componentes H₀"} ·
          muestras cada {episodeTiming(episode).sampleStepMs / 1000} segundos
        </span>
      </div>
    </section>
  );
}
