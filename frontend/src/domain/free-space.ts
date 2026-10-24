import { PITCH, distance } from "./types.ts";
import type { Point } from "./types.ts";

const STEP = 1;
const COLS = PITCH.length + 1,
  ROWS = PITCH.width + 1;
const index = (x: number, y: number) => y * COLS + x;
const point = (i: number): Point => ({ x: i % COLS, y: Math.floor(i / COLS) });
const neighbors = (i: number) => {
  const { x, y } = point(i);
  return [
    x > 0 ? i - 1 : -1,
    x + 1 < COLS ? i + 1 : -1,
    y > 0 ? i - COLS : -1,
    y + 1 < ROWS ? i + COLS : -1,
  ].filter((j) => j >= 0);
};

/** Four-neighbor, 1 m grid approximation; boundary nodes are not joined outside the pitch. */
export function freeSpace(
  defenders: Point[],
  radius: number,
  ball: Point | null,
  attackRight: boolean,
) {
  const clearance = new Float64Array(COLS * ROWS),
    labels = new Int32Array(COLS * ROWS).fill(-1);
  for (let i = 0; i < clearance.length; i++)
    clearance[i] = defenders.length
      ? Math.min(...defenders.map((p) => distance(p, point(i))))
      : Infinity;
  const regions: { size: number; boundary: boolean }[] = [];
  for (let i = 0; i < labels.length; i++) {
    if (labels[i] !== -1 || clearance[i] < radius) continue;
    const label = regions.length,
      queue = [i];
    labels[i] = label;
    let boundary = false;
    for (let head = 0; head < queue.length; head++) {
      const q = queue[head],
        p = point(q);
      boundary ||=
        p.x === 0 || p.x === PITCH.length || p.y === 0 || p.y === PITCH.width;
      for (const n of neighbors(q))
        if (labels[n] === -1 && clearance[n] >= radius) {
          labels[n] = label;
          queue.push(n);
        }
    }
    regions.push({ size: queue.length, boundary });
  }
  const route: Point[] = [];
  let reachable = false,
    startCovered = false;
  if (ball) {
    const start = index(
      Math.max(0, Math.min(105, Math.round(ball.x))),
      Math.max(0, Math.min(68, Math.round(ball.y))),
    );
    startCovered = clearance[start] < radius;
    if (!startCovered) {
      const queue = [start],
        previous = new Int32Array(labels.length).fill(-1);
      previous[start] = start;
      for (let head = 0; head < queue.length; head++) {
        const q = queue[head],
          p = point(q);
        if ((attackRight ? p.x >= 100 : p.x <= 5) && p.y >= 24 && p.y <= 44) {
          reachable = true;
          let current = q;
          while (current !== start) {
            route.push(point(current));
            current = previous[current];
          }
          route.push(point(start));
          route.reverse();
          break;
        }
        for (const n of neighbors(q))
          if (previous[n] === -1 && clearance[n] >= radius) {
            previous[n] = q;
            queue.push(n);
          }
      }
    }
  }
  // Compact horizontal runs keep the SVG light; display cells without changing connectivity.
  const runs: { x: number; y: number; width: number; label: number }[] = [];
  for (let y = 0; y < ROWS - 1; y++)
    for (let x = 0; x < COLS - 1;) {
      const label = labels[index(x, y)];
      if (label < 0) {
        x++;
        continue;
      }
      const start = x;
      while (x < COLS - 1 && labels[index(x, y)] === label) x++;
      runs.push({ x: start, y, width: x - start, label });
    }
  const regionAt = (p: Point): number | null => {
    if (p.x < 0 || p.x > PITCH.length || p.y < 0 || p.y > PITCH.width)
      return null;
    const value = labels[index(Math.round(p.x), Math.round(p.y))];
    return value < 0 ? null : value;
  };
  return {
    runs,
    regions,
    route,
    reachable,
    startCovered,
    step: STEP,
    regionAt,
  };
}
