import { beforeEach, describe, expect, it } from "vitest";

import {
  $canCancel,
  $coachingDisabled,
  $connection,
  $generationAvailable,
  $isStepConfirmed,
  $session,
  applyServerSnapshot,
  clearPendingTurn,
  markTurnPending,
  resetSession,
} from "./session";

beforeEach(() => {
  resetSession();
  $connection.set("idle");
});

describe("server authority", () => {
  it("starts with no stage and no confirmed step", () => {
    expect($session.get().stage).toBeNull();
    expect($session.get().confirmedSteps).toEqual([]);
  });

  it("takes stage and confirmed steps from the server", () => {
    applyServerSnapshot({ stage: "reality", confirmedSteps: ["pre_coaching", "goal"] });
    expect($session.get().stage).toBe("reality");
    expect($isStepConfirmed.get()("goal")).toBe(true);
  });

  it("exposes no way to confirm a step locally", () => {
    // A setter for this would let the UI show a gate the database never opened.
    const store = $session as unknown as Record<string, unknown>;
    for (const name of Object.keys(store)) {
      expect(name.toLowerCase()).not.toMatch(/confirmstep|advance|opengate/);
    }
  });

  it("treats a rollback as a plain server update", () => {
    applyServerSnapshot({ confirmedSteps: ["pre_coaching", "goal", "reality"] });
    applyServerSnapshot({ confirmedSteps: ["pre_coaching"], stage: "goal" });
    expect($isStepConfirmed.get()("goal")).toBe(false);
    expect($isStepConfirmed.get()("reality")).toBe(false);
  });

  it("carries the revision the server reported", () => {
    applyServerSnapshot({ revision: 4 });
    expect($session.get().revision).toBe(4);
  });
});

describe("safety", () => {
  it("leaves coaching enabled in normal state", () => {
    applyServerSnapshot({ safetyState: "normal" });
    expect($coachingDisabled.get()).toBe(false);
  });

  it("disables coaching entirely when urgent", () => {
    applyServerSnapshot({ safetyState: "urgent" });
    expect($coachingDisabled.get()).toBe(true);
  });

  it("disables coaching when possible_crisis, as the server does", () => {
    // This used to assert the opposite — that only urgent removed the surface.
    // The server disagrees, and the server is the one that decides:
    // `route_safety(POSSIBLE_CRISIS)` returns `coaching_interrupted`, the turn
    // service refuses the turn, and the system prompt says the same thing in
    // words. A composer left enabled here would invite the Coachee to write
    // something difficult and be answered with `safety_interrupted`.
    applyServerSnapshot({ safetyState: "possible_crisis" });
    expect($coachingDisabled.get()).toBe(true);
  });

  it("keeps coaching enabled while sensitive", () => {
    // Sensitive changes what the Coach asks; it does not take the session away.
    applyServerSnapshot({ safetyState: "sensitive" });
    expect($coachingDisabled.get()).toBe(false);
  });

  it("never lowers a safety state on its own", () => {
    applyServerSnapshot({ safetyState: "urgent" });
    applyServerSnapshot({ turns: [{ id: "t1", voice: "coachee", content: "ổn rồi" }] });
    expect($session.get().safetyState).toBe("urgent");
  });
});

describe("cancellation", () => {
  it("offers cancel only while a turn is in flight", () => {
    expect($canCancel.get()).toBe(false);
    markTurnPending("turn-1");
    expect($canCancel.get()).toBe(true);
    clearPendingTurn();
    expect($canCancel.get()).toBe(false);
  });
});

describe("degraded mode", () => {
  it("makes generation unavailable while offline", () => {
    $connection.set("offline");
    expect($generationAvailable.get()).toBe(false);
  });

  it("makes generation available when online and not urgent", () => {
    $connection.set("online");
    applyServerSnapshot({ safetyState: "normal" });
    expect($generationAvailable.get()).toBe(true);
  });

  it("keeps generation unavailable when urgent even if online", () => {
    $connection.set("online");
    applyServerSnapshot({ safetyState: "urgent" });
    expect($generationAvailable.get()).toBe(false);
  });

  it("keeps connection state separate from coaching state", () => {
    // Losing the socket must not look like a safety event, or vice versa.
    $connection.set("offline");
    expect($session.get().safetyState).toBe("normal");
  });
});

describe("reset", () => {
  it("clears everything a previous session left behind", () => {
    applyServerSnapshot({
      sessionId: "s1",
      stage: "will",
      revision: 7,
      confirmedSteps: ["goal"],
      candidates: [{ id: "c1", kind: "goal", value: "x" }],
    });
    markTurnPending("turn-9");
    resetSession();
    const session = $session.get();
    expect(session.sessionId).toBeNull();
    expect(session.revision).toBe(0);
    expect(session.confirmedSteps).toEqual([]);
    expect(session.candidates).toEqual([]);
    expect(session.pendingTurnId).toBeNull();
  });
});
