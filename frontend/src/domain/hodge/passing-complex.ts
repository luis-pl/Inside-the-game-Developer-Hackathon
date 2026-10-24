import type { CompletedPass } from "../types.ts";

export type ComplexMode = "clique" | "graph";
export interface PassingEdge {
  source: number;
  target: number;
  forward: number;
  backward: number;
  net: number;
}

/** Edges are supported by observed completed passes, including balanced pairs.
 * Canonical orientation is low player ID -> high player ID, not attack direction.
 */
export function passingComplex(
  passes: CompletedPass[],
  teamId: number,
  mode: ComplexMode,
  removedId: number | null = null,
) {
  const pairs = new Map<string, PassingEdge>();
  const seen = new Set<string>();
  let completedCount = 0;
  for (const pass of passes) {
    if (
      pass.teamId !== teamId ||
      pass.source === removedId ||
      pass.target === removedId ||
      pass.source === pass.target ||
      seen.has(pass.id)
    )
      continue;
    seen.add(pass.id);
    completedCount++;
    const source = Math.min(pass.source, pass.target),
      target = Math.max(pass.source, pass.target),
      key = `${source}:${target}`;
    const edge = pairs.get(key) ?? {
      source,
      target,
      forward: 0,
      backward: 0,
      net: 0,
    };
    if (pass.source === source) edge.forward++;
    else edge.backward++;
    edge.net = edge.forward - edge.backward;
    pairs.set(key, edge);
  }
  const edges = [...pairs.values()].sort(
    (a, b) => a.source - b.source || a.target - b.target,
  );
  const nodes = [...new Set(edges.flatMap((e) => [e.source, e.target]))].sort(
    (a, b) => a - b,
  );
  const incidence = nodes.map((id) =>
    edges.map((e) => Number(e.target === id) - Number(e.source === id)),
  );
  const triangles: number[][] = [];
  if (mode === "clique") {
    const edgeIndex = new Map(
      edges.map((e, i) => [`${e.source}:${e.target}`, i]),
    );
    for (let a = 0; a < nodes.length; a++)
      for (let b = a + 1; b < nodes.length; b++)
        for (let c = b + 1; c < nodes.length; c++) {
          const ab = edgeIndex.get(`${nodes[a]}:${nodes[b]}`),
            ac = edgeIndex.get(`${nodes[a]}:${nodes[c]}`),
            bc = edgeIndex.get(`${nodes[b]}:${nodes[c]}`);
          if (ab !== undefined && ac !== undefined && bc !== undefined) {
            const boundary = edges.map(() => 0);
            boundary[ab] = 1;
            boundary[ac] = -1;
            boundary[bc] = 1;
            triangles.push(boundary);
          }
        }
  }
  return { nodes, edges, incidence, triangles, completedCount, mode };
}
