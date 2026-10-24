import { test } from "node:test";
import assert from "node:assert/strict";
import {
  corridorClearance,
  distanceToSegment,
  isGabrielEdge,
} from "./corridors.ts";
import {
  clearanceForest,
  pathsFromBall,
  spatialNetwork,
} from "./clearance-network.ts";
import type { SpatialEdge, SpatialNode } from "./clearance-network.ts";
import { analyzeTactics } from "./tactics.ts";
import type { Frame, Player } from "./types.ts";

test("segment clearance detects a defender in the interior and respects end caps and boundaries", () => {
  const a = { x: 10, y: 20 },
    b = { x: 30, y: 20 };
  assert.equal(distanceToSegment({ x: 20, y: 25 }, a, b), 5);
  assert.equal(distanceToSegment({ x: 6, y: 20 }, a, b), 4);
  assert.equal(corridorClearance(a, b, [{ x: 20, y: 20 }]), 0);
  assert.equal(corridorClearance(a, b, [{ x: 20, y: 23 }]), 3);
  assert.equal(corridorClearance(a, b, []), 10);
});

test("Gabriel adjacency depends on empty geometry, not an edge length cutoff", () => {
  const a = { x: 5, y: 34 },
    b = { x: 100, y: 34 };
  assert.equal(isGabrielEdge(a, b, [a, b]), true);
  assert.equal(isGabrielEdge(a, b, [a, b, { x: 50, y: 34 }]), false);
  assert.equal(isGabrielEdge(a, b, [a, b, { x: 50, y: 0 }]), false);
  assert.equal(isGabrielEdge(a, a, [a]), false);
});

test("a defender removes a direct connection while a companion becomes a relay", () => {
  const nodes = [
    { id: "ball", x: 10, y: 34 },
    { id: "p", x: 30, y: 34 },
  ];
  const defender = { x: 20, y: 34 };
  assert.equal(
    spatialNetwork(nodes, [defender], [...nodes, defender]).edges.length,
    0,
  );
  const relay = { id: "relay", ...defender };
  const network = spatialNetwork([...nodes, relay], [], [...nodes, relay]);
  assert.deepEqual(
    network.paths.get("p")?.nodes.map((n) => n.id),
    ["ball", "relay", "p"],
  );
});

test("H0 forest preserves widest-path reachability at every critical clearance", () => {
  const nodes: SpatialNode[] = ["ball", "a", "b", "c", "isolated"].map(
    (id, i) => ({ id, x: 10 + i * 5, y: 20 }),
  );
  const edge = (a: number, b: number, clearance: number): SpatialEdge => ({
    a: nodes[a],
    b: nodes[b],
    clearance,
    length: 1,
  });
  const edges = [
    edge(0, 1, 2),
    edge(0, 2, 6),
    edge(2, 1, 5),
    edge(1, 3, 4),
    edge(2, 3, 1),
  ];
  const result = clearanceForest(nodes, edges),
    paths = pathsFromBall(nodes, result.forest);
  assert.equal(paths.get("a")!.clearance, 5);
  assert.equal(paths.get("c")!.clearance, 4);
  assert.equal(paths.has("isolated"), false);
  assert.equal(result.components, 2);
  for (const threshold of [0, 1, 2, 4, 5, 6, 7]) {
    const reached = new Set(["ball"]);
    let change = true;
    while (change) {
      change = false;
      for (const e of edges)
        if (e.clearance >= threshold) {
          if (reached.has(e.a.id) && !reached.has(e.b.id)) {
            reached.add(e.b.id);
            change = true;
          }
          if (reached.has(e.b.id) && !reached.has(e.a.id)) {
            reached.add(e.a.id);
            change = true;
          }
        }
    }
    assert.deepEqual(
      [...paths]
        .filter(([, p]) => p.clearance >= threshold)
        .map(([id]) => id)
        .sort(),
      [...reached].sort(),
    );
  }
});

const player = (id: number, teamId: number, x: number, y: number): Player => ({
  id,
  teamId,
  x,
  y,
  number: id,
  name: `P${id}`,
  goalkeeper: false,
});
const frame: Frame = {
  timeMs: 0,
  ballInPlay: true,
  ball: { x: 25, y: 34 },
  players: [
    player(1, 1, 40, 20),
    player(2, 1, 60, 20),
    player(3, 1, 60, 48),
    player(4, 1, 40, 48),
    player(5, 2, 32, 34),
    player(6, 2, 50, 34),
    player(7, 2, 70, 34),
  ],
};

test("spaces are Voronoi clearances, paths start at the ball and spaces never relay", () => {
  const result = analyzeTactics(frame, 1, true);
  assert.ok(result.openings.length > 0);
  assert.equal(
    result.network.nodes.some((n) => n.id === "space"),
    false,
  );
  for (const o of result.openings) {
    assert.ok(o.diameter > 0);
    if (!o.path) continue;
    assert.equal(o.path.nodes[0].id, "ball");
    assert.equal(o.path.nodes.at(-1)!.id, "space");
    assert.equal(
      o.path.nodes.slice(0, -1).some((n) => n.id === "space"),
      false,
    );
    for (let i = 1; i < o.path.nodes.length; i++)
      for (const d of frame.players.filter((p) => p.teamId === 1)) {
        assert.ok(
          distanceToSegment(d, o.path.nodes[i - 1], o.path.nodes[i]) >=
            o.path.clearance - 1e-8,
        );
      }
  }
});

test("missing ball gives unknown access; a defender at the ball prevents positive-clearance exits", () => {
  const missing = analyzeTactics({ ...frame, ball: null }, 1, true);
  assert.equal(missing.receiver, null);
  assert.ok(missing.openings.every((o) => o.ballConnected === null));
  const covered = analyzeTactics({ ...frame, ball: { x: 40, y: 20 } }, 1, true);
  assert.equal(covered.reachablePlayers, 0);
  assert.ok(covered.openings.every((o) => o.path === null));
});

test("pitch reflection preserves connections and their measured widths", () => {
  const nodes = [
    { id: "ball", x: 20, y: 25 },
    { id: "p", x: 40, y: 25 },
    { id: "q", x: 40, y: 40 },
  ];
  const defenders = [{ x: 30, y: 40 }];
  const first = spatialNetwork(nodes, defenders, [...nodes, ...defenders]);
  // Reflection keeps the field and all widths invariant, with no manual parameters.
  const reflect = <T extends { x: number; y: number }>(p: T): T => ({
    ...p,
    x: 105 - p.x,
  });
  const second = spatialNetwork(
    nodes.map(reflect),
    defenders.map(reflect),
    [...nodes, ...defenders].map(reflect),
  );
  assert.deepEqual(
    second.edges.map((e) => [e.a.id, e.b.id, e.clearance]),
    first.edges.map((e) => [e.a.id, e.b.id, e.clearance]),
  );
});
