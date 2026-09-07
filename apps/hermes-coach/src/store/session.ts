/**
 * Coaching session state, as reported by the server.
 *
 * Every field here is a copy of what the backend said. Nothing is derived: the
 * UI must never decide that a gate opened or a stage advanced, because the
 * server is the only place that knows whether the Coachee's answer actually
 * qualified. A client that computed those locally would render a step moving
 * forward that the database never recorded.
 *
 * `revision` is carried back on the next mutation so the server can reject a
 * command built on a view that has since moved on.
 */

import { atom, computed, map } from "nanostores";

export const STAGES = [
  "pre_coaching",
  "goal",
  "reality",
  "options",
  "will",
  "review",
] as const;

export type Stage = (typeof STAGES)[number];

export type SafetyState = "normal" | "sensitive" | "possible_crisis" | "urgent";

/** Who is speaking. The UI renders these three visibly differently. */
export type Voice = "coach" | "coachee" | "product_ui" | "safety_system";

export interface Turn {
  id: string;
  voice: Voice;
  content: string;
}

export interface Candidate {
  id: string;
  kind: "goal" | "insight" | "commitment" | "memory";
  value: string;
}

export interface SessionSnapshot {
  sessionId: string | null;
  stage: Stage | null;
  revision: number;
  /** Steps the server has confirmed. Never appended to locally. */
  confirmedSteps: Stage[];
  safetyState: SafetyState;
  turns: Turn[];
  candidates: Candidate[];
  /** The turn currently awaiting a reply, if any. Enables cancel. */
  pendingTurnId: string | null;
  /** Review was confirmed. The session takes no further turns. */
  ended: boolean;
}

export const EMPTY_SESSION: SessionSnapshot = {
  sessionId: null,
  stage: null,
  revision: 0,
  confirmedSteps: [],
  safetyState: "normal",
  turns: [],
  candidates: [],
  pendingTurnId: null,
  ended: false,
};

export const $session = map<SessionSnapshot>({ ...EMPTY_SESSION });

/** Set only from a server reply. */
export function applyServerSnapshot(snapshot: Partial<SessionSnapshot>): void {
  $session.set({ ...$session.get(), ...snapshot });
}

export function resetSession(): void {
  $session.set({ ...EMPTY_SESSION });
}

export function markTurnPending(turnId: string): void {
  $session.setKey("pendingTurnId", turnId);
}

export function clearPendingTurn(): void {
  $session.setKey("pendingTurnId", null);
}

export const $isStepConfirmed = computed($session, (session) => {
  const confirmed = new Set(session.confirmedSteps);
  return (stage: Stage) => confirmed.has(stage);
});

/**
 * Urgent safety replaces coaching entirely.
 *
 * Not a banner over a live composer: while urgent, the six-step controls are
 * gone, so there is no path to keep coaching through it.
 */
/** The states in which the server refuses a turn. Mirrors `route_safety`. */
export const INTERRUPTED_STATES: SafetyState[] = ["possible_crisis", "urgent"];

export function coachingInterrupted(state: SafetyState): boolean {
  return INTERRUPTED_STATES.includes(state);
}

export const $coachingDisabled = computed($session, (session) =>
  coachingInterrupted(session.safetyState),
);

/** Whether a turn is in flight, which is the only time cancel makes sense. */
export const $canCancel = computed(
  $session,
  (session) => session.pendingTurnId !== null,
);

/** Connection state, kept apart from coaching state: they fail differently. */
export type ConnectionState = "idle" | "connecting" | "online" | "offline";

export const $connection = atom<ConnectionState>("idle");

/**
 * Local functions stay usable when the model cannot be reached; only
 * generation is unavailable.
 */
export const $generationAvailable = computed(
  [$connection, $session],
  (connection, session) =>
    connection === "online" && !coachingInterrupted(session.safetyState),
);
