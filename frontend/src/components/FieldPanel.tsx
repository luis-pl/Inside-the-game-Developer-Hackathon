import { useEffect } from "react";
import type { CSSProperties } from "react";
import type { Lab } from "../hooks/use-lab.ts";
import { Pitch } from "./Pitch.tsx";
import { MatchPlayback, matchClock } from "./MatchPlayback.tsx";
import "./match-view.css";
import { episodeTiming, durationLabel } from "../domain/playback.ts";
import { connectionView } from "../domain/connection-view.ts";

export function FieldPanel({ lab }: { lab: Lab }) {
  const { frame, episode, analysis, tactics } = lab;
  const timing = episodeTiming(episode);
  useEffect(() => {
    if (episode) window.scrollTo({ top: 0, behavior: "instant" });
  }, [episode]);
  const defending = episode?.teams.find((t) => t.id === lab.teamId);
  const attacking = episode?.teams.find((t) => t.id !== lab.teamId);
  const leftTeam = episode?.teams[0] ?? defending;
  const rightTeam = episode?.teams[1] ?? attacking;
  const teamRole = (id: number | undefined, fallback: string) =>
    !episode
      ? fallback
      : id === lab.teamId
        ? "DEFIENDE"
        : lab.automaticTeam
          ? "ATAQUE ESTIMADO"
          : "ATACA";
  const view = lab.hodgeLayer !== "off" ? "passing" : lab.pitchView;
  const path = tactics?.featured?.path ?? tactics?.receiver?.path;
  const connections = tactics && frame ? connectionView(tactics, frame) : null;
  const teamColor = (id?: number) =>
    id === episode?.teams[1].id ? "#91dcc4" : "#e6b779";
  const choose = (next: typeof lab.pitchView) => {
    lab.setPitchView(next);
    lab.setHodgeLayer(next === "passing" ? "net" : "off");
  };
  return (
    <section className="match-screen" id="pitch-analysis">
      <div className="match-scoreboard">
        <div className="match-teams">
          <span
            className="defending-team"
            style={{ "--team-color": teamColor(leftTeam?.id) } as CSSProperties}
          >
            {leftTeam?.name ?? "Defensa"}
            <small>{teamRole(leftTeam?.id, "DEFIENDE")}</small>
          </span>
          <span className="match-versus">vs</span>
          <span
            className="attacking-team"
            style={
              { "--team-color": teamColor(rightTeam?.id) } as CSSProperties
            }
          >
            {rightTeam?.name ?? "Ataque"}
            <small>{teamRole(rightTeam?.id, "ATAQUE ESTIMADO")}</small>
          </span>
        </div>
        <div className="match-clock">
          <span>{episode?.period ?? 1}T</span>
          <strong>{frame ? matchClock(frame.timeMs) : "00:00"}</strong>
        </div>
        <span className={`play-state ${lab.playing ? "running" : ""}`}>
          {lab.playing ? "● REPRODUCIENDO" : "Ⅱ EN PAUSA"}
        </span>
      </div>
      <div className="match-signals" aria-live="off">
        {view === "openings" ? (
          <>
            <span className="space-signal">
              <i />
              {tactics?.featured ? (
                <>
                  Espacio libre <b>{tactics.featured.diameter.toFixed(0)} m</b>
                </>
              ) : (
                "Sin espacio destacado"
              )}
            </span>
            <span className="attacker-signal">
              <i />
              Enlazados al balón{" "}
              <b>
                {connections?.connected ?? 0}/{connections?.total ?? 0}
              </b>
              <small>{connections?.direct ?? 0} directos</small>
            </span>
            <span className="connection-signal">
              <i />
              {!frame?.ball ? (
                "Sin posición del balón"
              ) : path ? (
                <>
                  Corredor libre <b>{(2 * path.clearance).toFixed(1)} m</b>
                </>
              ) : (
                "Sin conexión desde el balón"
              )}
            </span>
          </>
        ) : view === "block" ? (
          <span>
            RED GEOMÉTRICA · {tactics?.network.edges.length ?? 0} conexiones ·{" "}
            {tactics?.reachablePlayers ?? 0} compañeros conectados al balón
          </span>
        ) : (
          <span>
            PASES DE {defending?.name} · TODA LA VENTANA · no corresponden al
            instante del reloj
          </span>
        )}
        {frame && !frame.ballInPlay && (
          <span className="stopped-ball">BALÓN DETENIDO</span>
        )}
        {lab.removed !== null && (
          <button
            className="simulation-flag"
            onClick={() => lab.setRemoved(null)}
          >
            SIMULACIÓN SIN JUGADOR · RESTAURAR ↺
          </button>
        )}
      </div>
      <div className="match-pitch">
        {frame && analysis && tactics ? (
          <Pitch
            frame={frame}
            analysis={analysis}
            tactics={tactics}
            broadcast={true}
            teamId={lab.teamId}
            mintTeamId={episode?.teams[1].id}
            removed={lab.removed}
            radius={0}
            coverage={false}
            spaces={false}
            connections={view === "block"}
            route={false}
            attackRight={lab.attackRight}
            onRemove={lab.setRemoved}
            hodge={lab.hodge}
            hodgeLayer={lab.hodgeLayer}
            showOpenings={false}
            selectedOpening={null}
            view={view}
          />
        ) : (
          <div className="match-empty">
            <h1>Un tiempo completo. Muchas jugadas.</h1>
            <button
              className="button mint"
              disabled={lab.loading || !lab.matchId}
              onClick={() => void lab.load()}
            >
              {lab.loading
                ? "Conectando con Azure…"
                : `▶ Cargar ${lab.durationSeconds / 60} minutos de partido`}
            </button>
            <a href="#match-settings">Elegir partido ↓</a>
          </div>
        )}
      </div>
      <MatchPlayback lab={lab} />
      <div className="match-source">
        <span>
          {episode?.source === "azure"
            ? "AZURE · DATOS SINTÉTICOS"
            : episode
              ? "EJEMPLO GEOMÉTRICO LOCAL"
              : "SIN DATOS CARGADOS"}{" "}
          · {(episode?.frames.length ?? 0).toLocaleString("es")} MUESTRAS ·{" "}
          {1000 / timing.sampleStepMs} Hz
        </span>
        <span>
          VENTANA DE {durationLabel(timing.durationMs)} ·{" "}
          {matchClock(timing.startMs)}–{matchClock(timing.endMs)}
          {" · "}1× = TIEMPO REAL
        </span>
      </div>
      <div className="match-layers" aria-label="Capa de la cancha">
        <span>Ver</span>
        <button
          aria-pressed={view === "openings"}
          onClick={() => choose("openings")}
        >
          Espacios y conexiones
        </button>
        <button aria-pressed={view === "block"} onClick={() => choose("block")}>
          Red completa
        </button>
        <button
          aria-pressed={view === "passing"}
          onClick={() => choose("passing")}
        >
          Pases acumulados
        </button>
      </div>
    </section>
  );
}
