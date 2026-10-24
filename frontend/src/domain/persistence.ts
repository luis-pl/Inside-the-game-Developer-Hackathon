import { distance } from "./types.ts";
import type { Bar, Point } from "./types.ts";

interface Simplex {
  vertices: number[];
  filtration: number;
}
const key = (vertices: number[]) => vertices.join(",");
const pivot = (column: Set<number>) => Math.max(...column);

/** Exact boundary reduction over F2 for the 2-skeleton of a Rips filtration.
 * Edge distance is the filtration parameter, not disk radius or elapsed time.
 */
export function persistence(points: Point[], cutoff = 40): Bar[] {
  const simplices: Simplex[] = points.map((_, i) => ({
    vertices: [i],
    filtration: 0,
  }));
  for (let i = 0; i < points.length; i++)
    for (let j = i + 1; j < points.length; j++) {
      const edge = distance(points[i], points[j]);
      if (edge <= cutoff)
        simplices.push({ vertices: [i, j], filtration: edge });
      for (let k = j + 1; k < points.length; k++) {
        const value = Math.max(
          edge,
          distance(points[i], points[k]),
          distance(points[j], points[k]),
        );
        if (value <= cutoff)
          simplices.push({ vertices: [i, j, k], filtration: value });
      }
    }
  simplices.sort(
    (a, b) =>
      a.filtration - b.filtration ||
      a.vertices.length - b.vertices.length ||
      key(a.vertices).localeCompare(key(b.vertices)),
  );
  const indices = new Map(simplices.map((s, i) => [key(s.vertices), i]));
  const reduced = new Map<number, Set<number>>(),
    births = new Set<number>(),
    deaths = new Map<number, number>();
  simplices.forEach((simplex, index) => {
    const boundary = new Set<number>();
    if (simplex.vertices.length > 1)
      simplex.vertices.forEach((_, omitted) =>
        boundary.add(
          indices.get(key(simplex.vertices.filter((_, i) => i !== omitted)))!,
        ),
      );
    while (boundary.size && reduced.has(pivot(boundary))) {
      for (const value of reduced.get(pivot(boundary))!) {
        if (boundary.has(value)) boundary.delete(value);
        else boundary.add(value);
      }
    }
    if (!boundary.size) births.add(index);
    else {
      const low = pivot(boundary);
      reduced.set(low, boundary);
      deaths.set(low, simplex.filtration);
    }
  });
  return [...births]
    .filter((i) => simplices[i].vertices.length <= 2)
    .map((i) => ({
      dimension: (simplices[i].vertices.length - 1) as 0 | 1,
      birth: simplices[i].filtration,
      death: deaths.get(i) ?? null,
    }))
    .filter((b) => b.death === null || b.death - b.birth > 1e-7);
}

export const bettiAt = (bars: Bar[], dimension: 0 | 1, epsilon: number) =>
  bars.filter(
    (b) =>
      b.dimension === dimension &&
      b.birth <= epsilon &&
      (b.death === null || epsilon < b.death),
  ).length;
