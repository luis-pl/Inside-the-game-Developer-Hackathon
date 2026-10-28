import test from "node:test";
import assert from "node:assert/strict";
import { workspaceApi, watchConversation } from "./workspace-network.ts";

test("an unanswered request times out instead of leaving the UI loading forever", async () => {
  const hung: typeof fetch = async (_url, options) =>
    new Promise((_resolve, reject) => {
      options!.signal!.addEventListener("abort", () =>
        reject(options!.signal!.reason),
      );
    });
  // Keep the event loop alive: native AbortSignal.timeout uses an unref'd timer.
  const keepAlive = setInterval(() => {}, 100);
  try {
    await assert.rejects(
      workspaceApi("conversations", {}, 10, hung),
      /REQUEST_TIMEOUT/,
    );
  } finally {
    clearInterval(keepAlive);
  }
});

test("expired sessions retain a specific code for the login recovery", async () => {
  const expired: typeof fetch = async () =>
    Response.json({ error: { code: "SESSION_EXPIRED" } }, { status: 401 });
  await assert.rejects(
    workspaceApi("conversations", {}, 100, expired),
    /SESSION_EXPIRED/,
  );
});

test("polling stops after a failure, without assuming the server finished", async () => {
  let attempts = 0;
  let states = 0;
  let stop = () => {};
  await new Promise<void>((resolve) => {
    stop = watchConversation(
      async () => {
        attempts++;
        throw Error("REQUEST_TIMEOUT");
      },
      () => {
        states++;
        return true;
      },
      () => {
        setTimeout(resolve, 15);
      },
      1,
    );
  });
  stop();
  assert.equal(attempts, 1);
  assert.equal(states, 0);
});

test("slow polling does not overlap and stops when the real state is complete", async () => {
  let inFlight = 0,
    maxInFlight = 0,
    calls = 0;
  let stop = () => {};
  await new Promise<void>((resolve) => {
    stop = watchConversation(
      async () => {
        inFlight++;
        maxInFlight = Math.max(maxInFlight, inFlight);
        await new Promise((r) => setTimeout(r, 5));
        inFlight--;
        return { busy: ++calls < 3 };
      },
      (state) => {
        if (!state.busy) resolve();
        return state.busy;
      },
      (error) => {
        throw error;
      },
      1,
    );
  });
  stop();
  assert.equal(maxInFlight, 1);
  assert.equal(calls, 3);
});

test("closing a conversation aborts its pending status request", async () => {
  let aborted = false,
    delivered = false;
  const stop = watchConversation(
    async (signal) =>
      new Promise((_, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(Error("aborted"));
        });
      }),
    () => {
      delivered = true;
      return true;
    },
    () => {
      delivered = true;
    },
  );
  stop();
  await Promise.resolve();
  assert.equal(aborted, true);
  assert.equal(delivered, false);
});
