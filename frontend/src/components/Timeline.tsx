import { useId, useMemo, useState } from "react";
import type { PointerEvent } from "react";
import type { Lab } from "../hooks/use-lab.ts";
import { episodeTiming } from "../domain/playback.ts";
import { chartSegments, nearestSample } from "../domain/chart-series.ts";
import { matchClock } from "./MatchPlayback.tsx";

export function Timeline({ lab }: { lab: Lab }) {
  const [metric, setMetric] = useState<"openings" | "groups">("openings");
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  const gradientId = useId();
  const samples = useMemo(
    () =>
      (lab.episode?.frames ?? []).map((frame, i) => ({
        timeMs: frame.timeMs,
        value:
          frame.players.length < 3 || (metric === "groups" && !frame.ball)
            ? null
            : metric === "openings"
              ? (lab.openingSeries[i] ?? null)
              : (lab.tacticalSeries[i]?.network.components ?? null),
      })),
    [lab.episode, lab.openingSeries, lab.tacticalSeries, metric],
  );
  const timing = episodeTiming(lab.episode);
  const segments = useMemo(
    () => chartSegments(samples, timing.sampleStepMs * 1.5),
    [samples, timing.sampleStepMs],
  );
  const maximum = Math.max(1, ...samples.map((p) => p.value ?? 0));
  const step =
    metric === "groups"
      ? Math.max(1, Math.ceil(maximum / 4))
      : Math.max(1, Math.ceil(maximum / 4 / 5) * 5);
  const upper = step * 4;
  const start = samples[0]?.timeMs ?? 0,
    end = samples.at(-1)?.timeMs ?? 1;
  const x = (ms: number) =>
    52 + ((ms - start) / Math.max(1, end - start)) * 710;
  const y = (value: number) => 202 - (value / upper) * 166;
  const inspected = samples[hover ?? lab.index];
  const unit = metric === "openings" ? "m" : "groups";
  function pointerIndex(event: PointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const fraction = Math.max(
      0,
      Math.min(
        1,
        (((event.clientX - bounds.left) / bounds.width) * 800 - 52) / 710,
      ),
    );
    return nearestSample(samples, start + fraction * (end - start));
  }
  function select(index: number) {
    if (index >= 0) {
      lab.setPlaying(false);
      lab.setIndex(index);
    }
  }
  return (
    <section className="spatial-trends panel" aria-label="Spatial trends">
      <div className="trend-heading">
        <div>
          <p className="section-label">THE MATCH, OVER TIME</p>
          <h2>Spatial trends</h2>
          <p>Find the moments when the shape changes.</p>
        </div>
        <button
          className="button secondary"
          disabled={!lab.episode || !lab.openingSeries.some((v) => v > 0)}
          onClick={() => {
            setMetric("openings");
            setHover(null);
            lab.goToOpening();
          }}
        >
          Jump to peak <span aria-hidden="true">↗</span>
        </button>
      </div>
      <div className="trend-toolbar">
        <div className="chart-switch" aria-label="Trend metric">
          <button
            aria-pressed={metric === "openings"}
            onClick={() => {
              setMetric("openings");
              setHover(null);
            }}
          >
            Highlighted space
          </button>
          <button
            aria-pressed={metric === "groups"}
            onClick={() => {
              setMetric("groups");
              setHover(null);
            }}
          >
            Network groups
          </button>
        </div>
        <div className="chart-readout">
          <span>{inspected ? matchClock(inspected.timeMs) : "—"}</span>
          <strong>
            {inspected?.value == null
              ? "—"
              : metric === "openings"
                ? inspected.value.toFixed(1)
                : inspected.value}{" "}
            <small>{unit}</small>
          </strong>
        </div>
      </div>
      {samples.length ? (
        <>
          <svg
            className="trend-chart"
            viewBox="0 0 800 240"
            role="img"
            aria-labelledby={titleId}
            onPointerMove={(e) => setHover(pointerIndex(e))}
            onPointerLeave={() => setHover(null)}
            onPointerDown={(e) => select(pointerIndex(e))}
          >
            <title id={titleId}>
              {metric === "openings"
                ? "Highlighted space diameter in metres"
                : "Number of connected network groups"}{" "}
              over match time. Use the slider below to inspect each sample. Gaps
              indicate missing tracking.
            </title>
            <defs>
              <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                <stop
                  offset="0%"
                  stopColor="var(--chart-ink)"
                  stopOpacity=".2"
                />
                <stop
                  offset="100%"
                  stopColor="var(--chart-ink)"
                  stopOpacity=".015"
                />
              </linearGradient>
            </defs>
            <text x="52" y="17" className="chart-unit">
              {metric === "openings"
                ? "SPACE DIAMETER (m)"
                : "CONNECTED GROUPS"}
            </text>
            {[0, 1, 2, 3, 4].map((i) => (
              <g key={i}>
                <line
                  x1="52"
                  x2="762"
                  y1={y(i * step)}
                  y2={y(i * step)}
                  className="chart-grid"
                />
                <text x="37" y={y(i * step) + 4} textAnchor="end">
                  {i * step}
                </text>
              </g>
            ))}
            {[0, 1, 2, 3, 4].map((i) => (
              <text key={i} x={52 + i * 177.5} y="228" textAnchor="middle">
                {matchClock(start + ((end - start) * i) / 4)}
              </text>
            ))}
            {segments.map((segment, i) => {
              const line = segment
                .map(
                  (p, j) =>
                    `${j ? "L" : "M"}${x(p.timeMs).toFixed(2)},${y(p.value!).toFixed(2)}`,
                )
                .join(" ");
              return (
                <g key={i}>
                  <path
                    d={`${line} L${x(segment.at(-1)!.timeMs)},202 L${x(segment[0].timeMs)},202 Z`}
                    fill={`url(#${gradientId})`}
                  />
                  <path d={line} className="chart-series" />
                  {segment.length === 1 && (
                    <circle
                      cx={x(segment[0].timeMs)}
                      cy={y(segment[0].value!)}
                      r="3"
                      fill="#26715c"
                    />
                  )}
                </g>
              );
            })}
            {inspected && (
              <g>
                <line
                  x1={x(inspected.timeMs)}
                  x2={x(inspected.timeMs)}
                  y1="32"
                  y2="202"
                  className="chart-cursor"
                />
                {inspected.value !== null && (
                  <circle
                    cx={x(inspected.timeMs)}
                    cy={y(inspected.value)}
                    r="5"
                    className="chart-dot"
                  />
                )}
              </g>
            )}
          </svg>
          <label className="chart-scrub-label" htmlFor={titleId + "-slider"}>
            Inspect match time{" "}
            <span>{matchClock(lab.episode!.frames[lab.index].timeMs)}</span>
          </label>
          <input
            id={titleId + "-slider"}
            className="chart-scrubber"
            aria-label="Inspect spatial trend sample"
            aria-valuetext={`${matchClock(lab.episode!.frames[lab.index].timeMs)}, ${samples[lab.index]?.value == null ? "no tracking data" : `${samples[lab.index].value!.toFixed(metric === "openings" ? 1 : 0)} ${unit}`}`}
            type="range"
            min="0"
            max={samples.length - 1}
            value={lab.index}
            onChange={(e) => {
              setHover(null);
              select(Number(e.target.value));
            }}
          />
        </>
      ) : (
        <div className="chart-empty">
          <span aria-hidden="true">∿</span>
          <strong>Your match timeline will appear here.</strong>
          <p>Load a recorded match or open the local geometric example.</p>
        </div>
      )}
      <p className="chart-footnote">
        <span className="series-key" />
        {metric === "openings"
          ? "Prioritised space diameter · connected spaces take precedence."
          : "Connected components in the ball-and-attackers network."}{" "}
        {lab.episode &&
          `Samples every ${timing.sampleStepMs / 1000}s. Select the chart or use the slider.`}
      </p>
    </section>
  );
}
