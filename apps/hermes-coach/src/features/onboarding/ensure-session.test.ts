import { describe, expect, it, vi } from "vitest";

import { CoachRpcError, type CoachApi } from "@/lib/coach-api";
import { ensureOnboardingSession } from "./ensure-session";

type Call = (method: string, params?: Record<string, unknown>) => Promise<unknown>;
type Mutate = (method: string, options: unknown) => Promise<unknown>;

const MISSING = {
  session_id: null,
  stage: null,
  revision: 0,
  confirmed_steps: [],
  safety_state: "normal",
  turns: [],
  candidates: [],
  ended: false,
};

const PRESENT = {
  ...MISSING,
  session_id: "onboarding",
  stage: "pre_coaching",
  revision: 1,
};

/** Answers `coach.session.state` from a script, one entry per read. */
function fakeApi(reads: unknown[], mutate?: ReturnType<typeof vi.fn<Mutate>>) {
  const remaining = [...reads];
  const onCall = vi.fn<Call>(async () => remaining.shift() ?? PRESENT);
  const onMutate = mutate ?? vi.fn<Mutate>(async () => ({}));
  return {
    api: { call: onCall, mutate: onMutate } as unknown as CoachApi,
    onCall,
    onMutate,
  };
}

describe("ensureOnboardingSession", () => {
  it("starts the session when there is none", async () => {
    const { api, onMutate } = fakeApi([MISSING, PRESENT]);
    await ensureOnboardingSession(api, "onboarding");
    expect(onMutate).toHaveBeenCalledOnce();
    expect(onMutate.mock.calls[0][0]).toBe("coach.session.start");
  });

  it("starts it under the id it was asked for", async () => {
    const { api, onMutate } = fakeApi([MISSING, PRESENT]);
    await ensureOnboardingSession(api, "onboarding");
    expect(onMutate.mock.calls[0][1]).toMatchObject({
      sessionId: "onboarding",
      revision: 0,
    });
  });

  it("does not start one that already exists", async () => {
    // The whole point of a fixed id: a reload rejoins rather than duplicates.
    const { api, onMutate } = fakeApi([PRESENT]);
    await ensureOnboardingSession(api, "onboarding");
    expect(onMutate).not.toHaveBeenCalled();
  });

  it("returns the state the server reports after starting", async () => {
    const { api } = fakeApi([MISSING, PRESENT]);
    const state = await ensureOnboardingSession(api, "onboarding");
    expect(state.session_id).toBe("onboarding");
    expect(state.revision).toBe(1);
  });

  it("returns the existing state untouched", async () => {
    const { api } = fakeApi([PRESENT]);
    expect(await ensureOnboardingSession(api, "onboarding")).toMatchObject({
      session_id: "onboarding",
      revision: 1,
    });
  });

  it("re-reads after starting rather than guessing the new revision", async () => {
    // A guessed revision is the one thing the next mutation cannot survive.
    const { api, onCall } = fakeApi([MISSING, PRESENT]);
    await ensureOnboardingSession(api, "onboarding");
    expect(onCall.mock.calls.map((call) => call[0])).toEqual([
      "coach.session.state",
      "coach.session.state",
    ]);
  });

  it("treats a lost race as success when the session is there", async () => {
    // Two mounts can both read "missing" before either writes — React runs
    // effects twice in development. The loser is refused on revision, and that
    // refusal means the session exists, which is all this function promised.
    const onMutate = vi.fn<Mutate>(async () => {
      throw new CoachRpcError("stale_revision", "revision moved");
    });
    const { api } = fakeApi([MISSING, PRESENT], onMutate);
    const state = await ensureOnboardingSession(api, "onboarding");
    expect(state.session_id).toBe("onboarding");
  });

  it("still fails when the start failed and no session appeared", async () => {
    // Swallowing this would hand the caller a session id of null and let the
    // records step run against nothing.
    const onMutate = vi.fn<Mutate>(async () => {
      throw new CoachRpcError("stale_revision", "revision moved");
    });
    const { api } = fakeApi([MISSING, MISSING], onMutate);
    await expect(ensureOnboardingSession(api, "onboarding")).rejects.toThrow();
  });

  it("does not swallow a transport failure on the first read", async () => {
    const onCall = vi.fn<Call>(async () => {
      throw new Error("socket closed");
    });
    const api = { call: onCall, mutate: vi.fn() } as unknown as CoachApi;
    await expect(ensureOnboardingSession(api, "onboarding")).rejects.toThrow(
      "socket closed",
    );
  });
});
