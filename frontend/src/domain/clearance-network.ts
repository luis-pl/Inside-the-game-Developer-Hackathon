import type { Point } from "./types.ts";
import { distance } from "./types.ts";
import { corridorClearance, isGabrielEdge } from "./corridors.ts";

export interface SpatialNode extends Point {
  id: string;
  playerId?: number;
  number?: number;
}
export interface SpatialEdge {
  a: SpatialNode;
  b: SpatialNode;
  clearance: number;
  length: number;
}
export interface SpatialPath {
  nodes: SpatialNode[];
  clearance: number;
  length: number;
}
export interface Merge {
  clearance: number;
  components: number;
}

/** Kruskal on descending clearance is the H0 superlevel filtration of this
 * weighted graph. Its maximum spanning forest preserves every widest path.
 */
export function clearanceForest(nodes: SpatialNode[], edges: SpatialEdge[]) {
  const parents = new Map(nodes.map((n) => [n.id, n.id]));
  const root = (id: string): string => {
    let current = id;
    while (parents.get(current) !== current) current = parents.get(current)!;
    return current;
  };
  const forest: SpatialEdge[] = [],
    merges: Merge[] = [];
  let components = nodes.length;
  for (const edge of [...edges].sort(
    (a, b) =>
      b.clearance - a.clearance ||
      a.length - b.length ||
      a.a.id.localeCompare(b.a.id) ||
      a.b.id.localeCompare(b.b.id),
  )) {
    const a = root(edge.a.id),
      b = root(edge.b.id);
    if (a === b) continue;
    parents.set(a, b);
    forest.push(edge);
    merges.push({ clearance: edge.clearance, components: --components });
  }
  return { forest, merges, components };
}

export function pathsFromBall(nodes: SpatialNode[], forest: SpatialEdge[]) {
  const paths = new Map<string, SpatialPath>();
  const ball = nodes.find((n) => n.id === "ball");
  if (!ball) return paths;
  paths.set(ball.id, { nodes: [ball], clearance: Infinity, length: 0 });
  const queue = [ball];
  for (let i = 0; i < queue.length; i++) {
    const node = queue[i],
      before = paths.get(node.id)!;
    for (const edge of forest) {
      const next =
        edge.a.id === node.id ? edge.b : edge.b.id === node.id ? edge.a : null;
      if (!next || paths.has(next.id)) continue;
      paths.set(next.id, {
        nodes: [...before.nodes, next],
        clearance: Math.min(before.clearance, edge.clearance),
        length: before.length + edge.length,
      });
      queue.push(next);
    }
  }
  return paths;
}

export function spatialNetwork(
  nodes: SpatialNode[],
  defenders: Point[],
  sites: Point[],
) {
  const edges: SpatialEdge[] = [];
  for (let i = 0; i < nodes.length; i++)
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i],
        b = nodes[j];
      if (!isGabrielEdge(a, b, sites)) continue;
      const clearance = corridorClearance(a, b, defenders);
      if (clearance <= 1e-9) continue;
      edges.push({ a, b, clearance, length: distance(a, b) });
    }
  const filtration = clearanceForest(nodes, edges);
  return {
    nodes,
    edges,
    ...filtration,
    paths: pathsFromBall(nodes, filtration.forest),
  };
}
