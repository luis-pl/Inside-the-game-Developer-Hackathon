import { distance, PITCH } from "./types.ts";
import type { Player, Point } from "./types.ts";

export interface Opening {
  id: string;
  center: Point;
  radius: number;
  diameter: number;
  support: number[];
  ballConnected: boolean | null;
}
const cross = (a: Point, b: Point, c: Point) =>
  (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);

function convexHull(points: Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const half = (values: Point[]) => {
    const result: Point[] = [];
    for (const p of values) {
      while (
        result.length >= 2 &&
        cross(result.at(-2)!, result.at(-1)!, p) <= 1e-9
      )
        result.pop();
      result.push(p);
    }
    return result;
  };
  const lower = half(sorted),
    upper = half([...sorted].reverse());
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}
function insideHull(point: Point, hull: Point[]) {
  return (
    hull.length >= 3 &&
    hull.every((p, i) => cross(p, hull[(i + 1) % hull.length], point) >= -1e-7)
  );
}
function circumcenter(a: Point, b: Point, c: Point): Point | null {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-8) return null;
  const aa = a.x * a.x + a.y * a.y,
    bb = b.x * b.x + b.y * b.y,
    cc = c.x * c.x + c.y * c.y;
  return {
    x: (aa * (b.y - c.y) + bb * (c.y - a.y) + cc * (a.y - b.y)) / d,
    y: (aa * (c.x - b.x) + bb * (a.x - c.x) + cc * (b.x - a.x)) / d,
  };
}

/** Empty circumcircle candidates inside the outfield hull. The displayed disk
 * subtracts the coverage radius and is clipped to fit inside the pitch.
 * These are geometric clearances, not H1 classes or interception probabilities.
 */
export function findOpenings(
  players: Player[],
  coverageRadius: number,
  ball: Point | null = null,
  regionAt?: (point: Point) => number | null,
): Opening[] {
  const outfield = players.filter((p) => !p.goalkeeper),
    hull = convexHull(outfield);
  const candidates: Opening[] = [];
  for (let i = 0; i < outfield.length; i++)
    for (let j = i + 1; j < outfield.length; j++)
      for (let k = j + 1; k < outfield.length; k++) {
        const support = [outfield[i], outfield[j], outfield[k]],
          center = circumcenter(support[0], support[1], support[2]);
        if (
          !center ||
          !insideHull(center, hull) ||
          center.x < 0 ||
          center.x > 105 ||
          center.y < 0 ||
          center.y > 68
        )
          continue;
        const nearest = Math.min(...players.map((p) => distance(p, center)));
        if (nearest < distance(center, support[0]) - 1e-6) continue;
        const radius = Math.min(
          nearest - coverageRadius,
          center.x,
          PITCH.length - center.x,
          center.y,
          PITCH.width - center.y,
        );
        if (
          radius < 1 ||
          candidates.some((p) => distance(p.center, center) < 1e-6)
        )
          continue;
        const ballRegion = ball && regionAt ? regionAt(ball) : null,
          centerRegion = regionAt?.(center) ?? null;
        candidates.push({
          id: "",
          center,
          radius,
          diameter: radius * 2,
          support: support.map((p) => p.id),
          ballConnected:
            !ball || !regionAt
              ? null
              : ballRegion !== null && ballRegion === centerRegion,
        });
      }
  candidates.sort(
    (a, b) =>
      b.radius - a.radius || a.center.x - b.center.x || a.center.y - b.center.y,
  );
  const chosen: Opening[] = [];
  for (const candidate of candidates) {
    if (
      chosen.every(
        (other) =>
          distance(candidate.center, other.center) >
          0.75 * (candidate.radius + other.radius),
      )
    )
      chosen.push({ ...candidate, id: `A${chosen.length + 1}` });
    if (chosen.length === 3) break;
  }
  return chosen;
}
