import { useCallback, useEffect, useRef, useState } from "react";
import type { Episode } from "../domain/types.ts";
import { sampleIndexAt } from "../domain/interpolation.ts";
import { advanceReplayTime } from "../domain/playback.ts";

/** Continuous match clock, independent of source sampling and render cadence. */
export function useReplayClock(
  episode: Episode | null,
  playing: boolean,
  speed: number,
  stop: (value: boolean) => void,
) {
  const [timeMs, setTimeMs] = useState(0);
  const [seekVersion, setSeekVersion] = useState(0);
  const current = useRef(0);
  const seekTime = useCallback(
    (value: number) => {
      if (!episode) return;
      const next = Math.max(
        episode.frames[0].timeMs,
        Math.min(episode.window?.endMs ?? episode.frames.at(-1)!.timeMs, value),
      );
      current.current = next;
      setTimeMs(next);
      setSeekVersion((value) => value + 1);
    },
    [episode],
  );
  useEffect(() => {
    current.current = episode?.frames[0]?.timeMs ?? 0;
    setTimeMs(current.current);
  }, [episode]);
  useEffect(() => {
    if (!playing || !episode) return;
    const start = current.current,
      end = episode.window?.endMs ?? episode.frames.at(-1)!.timeMs;
    const origin = performance.now();
    let request = 0,
      lastPaint = -Infinity;
    const tick = (now: number) => {
      const next = advanceReplayTime(start, now - origin, speed, end);
      if (now - lastPaint >= 1000 / 30 || next === end) {
        current.current = next;
        setTimeMs(next);
        lastPaint = now;
      }
      if (next === end) stop(false);
      else request = requestAnimationFrame(tick);
    };
    request = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(request);
  }, [episode, playing, speed, stop, seekVersion]);
  const playheadMs = episode
    ? Math.max(
        episode.frames[0].timeMs,
        Math.min(
          episode.window?.endMs ?? episode.frames.at(-1)!.timeMs,
          timeMs,
        ),
      )
    : 0;
  const index = episode ? sampleIndexAt(episode.frames, playheadMs) : 0;
  const setIndex = (value: number) => {
    const frame = episode?.frames[value];
    if (frame) seekTime(frame.timeMs);
  };
  return { playheadMs, seekTime, index, setIndex };
}
