import { test } from "node:test";
import assert from "node:assert/strict";
import { findOpenings } from "./openings.ts";
import { distance } from "./types.ts";
import type { Player } from "./types.ts";
import { freeSpace } from "./free-space.ts";
const player = (id: number, x: number, y: number): Player => ({
  id,
  x,
  y,
  teamId: 1,
  number: id,
  name: `P${id}`,
  goalkeeper: false,
});
const square = [
  player(1, 40, 20),
  player(2, 60, 20),
  player(3, 60, 40),
  player(4, 40, 40),
];

test("square yields a central free circle reduced by defender coverage", () => {
  const gaps = findOpenings(square, 4);
  assert.equal(gaps.length, 1);
  assert.ok(Math.abs(gaps[0].center.x - 50) < 1e-8);
  assert.ok(Math.abs(gaps[0].radius - (Math.sqrt(200) - 4)) < 1e-8);
  for (let angle = 0; angle < 2 * Math.PI; angle += 0.1) {
    const p = {
      x: 50 + gaps[0].radius * Math.cos(angle),
      y: 30 + gaps[0].radius * Math.sin(angle),
    };
    assert.ok(square.every((defender) => distance(defender, p) >= 4 - 1e-7));
  }
});
test("collinear players, closed gaps and fewer than three players create no openings", () => {
  assert.deepEqual(findOpenings(square.slice(0, 2), 1), []);
  assert.deepEqual(
    findOpenings([player(1, 20, 30), player(2, 40, 30), player(3, 60, 30)], 1),
    [],
  );
  assert.deepEqual(findOpenings(square, 15), []);
});
test("a goalkeeper inside a candidate prevents a false central gap", () => {
  const keeper = { ...player(5, 50, 30), goalkeeper: true };
  assert.deepEqual(findOpenings([...square, keeper], 4), []);
});
test("an opening can exist while the ball is covered", () => {
  const ball = { x: 40, y: 20 },
    free = freeSpace(square, 4, ball, true),
    opening = findOpenings(square, 4, ball, free.regionAt)[0];
  assert.equal(opening.ballConnected, false);
  const central = { x: 50, y: 30 },
    open = freeSpace(square, 4, central, true);
  assert.equal(
    findOpenings(square, 4, central, open.regionAt)[0].ballConnected,
    true,
  );
});
test("circles fit inside the pitch and larger coverage cannot widen a surviving opening", () => {
  const small = findOpenings(square, 3)[0],
    large = findOpenings(square, 5)[0];
  assert.ok(large.radius < small.radius);
  assert.ok(
    small.center.x - small.radius >= 0 && small.center.x + small.radius <= 105,
  );
  assert.ok(
    small.center.y - small.radius >= 0 && small.center.y + small.radius <= 68,
  );
});
