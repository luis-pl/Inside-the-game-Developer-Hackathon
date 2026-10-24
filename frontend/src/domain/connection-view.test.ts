import { test } from "node:test";
import assert from "node:assert/strict";
import { connectionView, projectNode } from "./connection-view.ts";
import { inferAttackingTeams } from "./attacking-team.ts";
import { analyzeTactics } from "./tactics.ts";
import type { Episode, Frame, Player } from "./types.ts";

const player = (id: number, teamId: number, x: number): Player => ({
  id,
  teamId,
  x,
  y: 20,
  name: String(id),
  number: id,
  goalkeeper: false,
});
const frame: Frame = {
  timeMs: 0,
  ballInPlay: true,
  ball: { x: 10, y: 20 },
  players: [
    player(101, 1, 10),
    player(102, 1, 20),
    player(103, 1, 60),
    player(104, 1, 70),
    player(201, 2, 40),
  ],
};

test("show every attacker and preserve disconnected support edges instead of only one selected path", () => {
  const tactics = analyzeTactics(frame, 2, true),
    view = connectionView(tactics, frame);
  assert.equal(view.total, 4);
  assert.equal(view.connected, 2);
  assert.equal(view.direct, 1);
  assert.deepEqual(
    view.nodes.map((n) => n.kind),
    ["source", "direct", "separate", "separate"],
  );
  assert.ok(view.edges.some((e) => e.kind === "direct"));
  assert.ok(
    view.edges.some(
      (e) =>
        e.kind === "separate" && e.a.playerId === 103 && e.b.playerId === 104,
    ),
  );
  assert.equal(view.edges.length, tactics.network.edges.length);
  const moving = { ...frame, ball: { x: 11, y: 20 } };
  assert.equal(
    connectionView(tactics, moving).nodes.find((n) => n.player.id === 101)!
      .kind,
    "source",
  );
});

test("projected endpoints follow moving players without replacing spatial node identities", () => {
  const node = { id: "player:102", playerId: 102, x: 20, y: 20 };
  const moving = {
    ...frame,
    players: frame.players.map((p) => (p.id === 102 ? { ...p, x: 21 } : p)),
  };
  assert.deepEqual(projectNode(node, moving), { ...node, x: 21 });
  assert.equal(projectNode(node, { ...frame, players: [] }), null);
  assert.equal(
    projectNode({ id: "ball", x: 0, y: 0 }, { ...frame, ball: null }),
    null,
  );
});

const episode = (frames: Frame[]): Episode => ({
  frames,
  teams: [
    { id: 1, name: "A" },
    { id: 2, name: "B" },
  ],
  source: "local",
  warnings: [],
  matchLabel: "test",
  period: 1,
  homeAttacksRight: true,
  events: [],
  passes: [],
});
const duel: Frame = { ...frame, players: [player(1, 1, 10), player(2, 2, 90)] };

test("attacking team follows nearest player and changes when the other team is nearest", () => {
  const selections = inferAttackingTeams(
    episode([
      { ...duel, ball: { x: 12, y: 20 } },
      { ...duel, ball: { x: 88, y: 20 } },
    ]),
  );
  assert.deepEqual(
    selections.map((s) => [
      s.attackingTeamId,
      s.defendingTeamId,
      s.nearestPlayerId,
    ]),
    [
      [1, 2, 1],
      [2, 1, 2],
    ],
  );
});

test("ties, stoppages and missing-ball frames preserve the preceding estimate", () => {
  const selections = inferAttackingTeams(
    episode([
      { ...duel, ball: { x: 88, y: 20 } },
      { ...duel, ball: { x: 50, y: 20 } },
      { ...duel, ball: { x: 12, y: 20 }, ballInPlay: false },
      { ...duel, ball: null },
    ]),
  );
  assert.deepEqual(
    selections.map((s) => s.attackingTeamId),
    [2, 2, 2, 2],
  );
  assert.deepEqual(
    selections.map((s) => s.reason),
    ["nearest", "tie", "held", "held"],
  );
});

test("absent ball produces no direct or reachable attackers", () => {
  const missing = { ...frame, ball: null };
  const view = connectionView(analyzeTactics(missing, 2, true), missing);
  assert.equal(view.connected, 0);
  assert.equal(view.direct, 0);
});
