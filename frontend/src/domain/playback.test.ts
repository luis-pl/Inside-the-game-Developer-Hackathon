import { test } from "node:test";
import assert from "node:assert/strict";
import {
  frameDelayMs,
  episodeTiming,
  advanceReplayTime,
  nextAction,
} from "./playback.ts";
import { localScenario } from "../data/local-scenario.ts";
import { MemoryEpisodeRepository } from "../data/memory-repository.ts";
import type { EpisodeQuery, EpisodeRepository } from "./types.ts";

test("1x is real time and each speed is a literal multiplier of elapsed screen time", () => {
  assert.equal(advanceReplayTime(600000, 1000, 1, 2700000), 601000);
  assert.equal(advanceReplayTime(600000, 1000, 0.5, 2700000), 600500);
  assert.equal(advanceReplayTime(600000, 1000, 2, 2700000), 602000);
  assert.equal(advanceReplayTime(600000, 1000, 4, 2700000), 604000);
  assert.equal(advanceReplayTime(600000, 1000, 8, 2700000), 608000);
  assert.equal(advanceReplayTime(2698000, 1000, 1, 2699000), 2699000);
});

test("next action visits actual recorded events and wraps after the last action", () => {
  const episode = {
    ...localScenario(),
    events: [
      { timeMs: 10000, label: "Pass" },
      { timeMs: 20000, label: "Shot" },
    ],
  };
  assert.equal(nextAction(episode, 0)!.timeMs, 10000);
  assert.equal(nextAction(episode, 11000)!.timeMs, 20000);
  assert.equal(nextAction(episode, 21000)!.timeMs, 10000);
});

test("memory cache distinguishes different requested durations", async () => {
  let count = 0;
  const memory = new MemoryEpisodeRepository({
    matches: async () => [],
    episode: async () => {
      count++;
      return localScenario();
    },
  });
  const query = { matchId: 1, period: 1, startSeconds: 0 };
  await memory.episode({ ...query, durationSeconds: 900 });
  await memory.episode({ ...query, durationSeconds: 2700 });
  await memory.episode({ ...query, durationSeconds: 900 });
  assert.equal(count, 2);
});

test("five-minute replay retains every one-second observation at each speed", () => {
  const episode = localScenario();
  assert.equal(episode.frames.length, 300);
  assert.deepEqual(episodeTiming(episode), {
    startMs: 600000,
    endMs: 900000,
    sampleStepMs: 1000,
    durationMs: 300000,
  });
  assert.equal(episode.frames.at(-1)!.timeMs, 899000);
  assert.equal(frameDelayMs(episode.frames, 0, 1), 1000);
  assert.equal(frameDelayMs(episode.frames, 0, 0.5), 2000);
  assert.equal(frameDelayMs(episode.frames, 0, 2), 500);
  assert.equal(frameDelayMs(episode.frames, 299, 1), null);
  const irregular = [
    episode.frames[0],
    { ...episode.frames[1], timeMs: 612000 },
  ];
  assert.equal(frameDelayMs(irregular, 0, 1), 12000);
});

test("cached windows replay without further requests and use LRU eviction", async () => {
  const calls: number[] = [],
    episode = localScenario();
  const source: EpisodeRepository = {
    matches: async () => [],
    episode: async (q) => {
      calls.push(q.startSeconds);
      return { ...episode, matchLabel: String(q.startSeconds) };
    },
  };
  const memory = new MemoryEpisodeRepository(source, 2);
  const query = (startSeconds: number): EpisodeQuery => ({
    matchId: 1,
    period: 1,
    startSeconds,
  });
  const first = await memory.episode(query(600));
  await memory.episode(query(900));
  assert.equal(await memory.episode(query(600)), first);
  await memory.episode(query(1200));
  await memory.episode(query(900));
  assert.deepEqual(calls, [600, 900, 1200, 900]);
});

test("failed or cancelled loads never poison the memory cache", async () => {
  let calls = 0;
  const source: EpisodeRepository = {
    matches: async () => [],
    episode: async () => {
      calls++;
      if (calls === 1) throw Error("failed");
      return localScenario();
    },
  };
  const memory = new MemoryEpisodeRepository(source),
    q = { matchId: 1, period: 1, startSeconds: 600 };
  await assert.rejects(memory.episode(q));
  const good = await memory.episode(q);
  assert.equal(await memory.episode(q), good);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(memory.episode(q, controller.signal), {
    name: "AbortError",
  });
  assert.equal(calls, 2);
});
