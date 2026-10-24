import { test } from "node:test";
import assert from "node:assert/strict";
import { decomposePassingFlow } from "./hodge/decomposition.ts";
import type { CompletedPass } from "./types.ts";

const passes = (arcs: number[][]): CompletedPass[] =>
  arcs.flatMap(([source, target, count = 1], index) =>
    Array.from({ length: count }, (_, i) => ({
      id: `${index}-${i}`,
      source,
      target,
      teamId: 1,
      timeMs: 1000,
    })),
  );
const near = (a: number, b: number) =>
  assert.ok(Math.abs(a - b) < 1e-9, `${a} differs from ${b}`);

test("a tree has only gradient flow, even with disconnected components", () => {
  const h = decomposePassingFlow(
    passes([
      [1, 2, 3],
      [2, 3],
      [4, 5, 2],
    ]),
    1,
  );
  near(h.fractions!.gradient, 1);
  near(h.fractions!.curl, 0);
  near(h.fractions!.harmonic, 0);
  assert.equal(h.firstBetti, 0);
  assert.ok(h.reliable);
});
test("a directed triangle is local curl when filled, harmonic when unfilled", () => {
  const p = passes([
      [1, 2],
      [2, 3],
      [3, 1],
    ]),
    filled = decomposePassingFlow(p, 1),
    graph = decomposePassingFlow(p, 1, "graph");
  near(filled.fractions!.curl, 1);
  near(filled.fractions!.harmonic, 0);
  assert.equal(filled.firstBetti, 0);
  near(graph.fractions!.harmonic, 1);
  near(graph.fractions!.curl, 0);
  assert.equal(graph.firstBetti, 1);
});
test("a square without diagonals has a nontrivial harmonic class", () => {
  const h = decomposePassingFlow(
    passes([
      [1, 2],
      [2, 3],
      [3, 4],
      [4, 1],
    ]),
    1,
  );
  near(h.fractions!.harmonic, 1);
  assert.equal(h.firstBetti, 1);
  assert.ok(h.reliable);
});
test("balanced passes retain support but have zero net energy and no percentages", () => {
  const h = decomposePassingFlow(
    passes([
      [1, 2],
      [2, 1],
    ]),
    1,
  );
  assert.equal(h.edges.length, 1);
  assert.equal(h.completedCount, 2);
  assert.equal(h.energy, 0);
  assert.equal(h.fractions, null);
});
test("filled tetrahedron handles dependent triangle boundaries without singular inversion", () => {
  const h = decomposePassingFlow(
    passes([
      [1, 2, 3],
      [1, 3],
      [1, 4, 2],
      [2, 3, 4],
      [2, 4],
      [3, 4, 3],
    ]),
    1,
  );
  assert.equal(h.triangles.length, 4);
  assert.equal(h.firstBetti, 0);
  assert.ok(h.reliable);
  near(h.energies.gradient + h.energies.curl + h.energies.harmonic, h.energy);
});
test("order, orientation changes and excluded nodes preserve the appropriate invariants", () => {
  const p = passes([
      [1, 2, 3],
      [2, 3],
      [3, 4, 2],
      [4, 1],
      [2, 4],
    ]),
    a = decomposePassingFlow(p, 1);
  const b = decomposePassingFlow(
    [...p]
      .reverse()
      .map((e) => ({ ...e, source: 10 - e.source, target: 10 - e.target })),
    1,
  );
  near(a.energies.gradient, b.energies.gradient);
  near(a.energies.curl, b.energies.curl);
  near(a.energies.harmonic, b.energies.harmonic);
  const removed = decomposePassingFlow(p, 1, "clique", 2);
  assert.ok(!removed.nodes.includes(2));
  assert.ok(removed.reliable);
});
test("duplicate event IDs, self passes and the other team are excluded", () => {
  const p = passes([[1, 2]]);
  const h = decomposePassingFlow(
    [
      ...p,
      ...p,
      { ...p[0], id: "own", target: 1 },
      { ...p[0], id: "other", teamId: 2 },
    ],
    1,
  );
  assert.equal(h.completedCount, 1);
  assert.equal(h.edges[0].net, 1);
  assert.equal(decomposePassingFlow([], 1).fractions, null);
});
test("mixed flow obeys Pythagoras and contains all three components", () => {
  const h = decomposePassingFlow(
    passes([
      [1, 2, 2],
      [2, 3, 2],
      [3, 1, 2],
      [4, 5, 2],
      [5, 6, 2],
      [6, 7, 2],
      [7, 4, 2],
      [3, 4, 2],
    ]),
    1,
  );
  near(h.fractions!.gradient, 0.125);
  near(h.fractions!.curl, 0.375);
  near(h.fractions!.harmonic, 0.5);
  assert.ok(h.reliable);
});
