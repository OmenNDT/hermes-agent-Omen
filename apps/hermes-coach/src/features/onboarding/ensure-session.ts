/**
 * Make sure the onboarding session exists before anything writes into it.
 *
 * Onboarding runs under one fixed session id, which is what lets a reload
 * rejoin the same records instead of stranding them. Nothing created it: the
 * records step read `coach.session.state` for an id that had never been
 * started, got a null session with an empty candidate list back, and offered
 * "create your first goal" as though every record had already been decided.
 *
 * Read then write, rather than a start that tolerates an existing session: the
 * server's `coach.session.start` means "begin a new one", and widening it to
 * "begin or adopt" would make a duplicate start look successful everywhere else
 * in the app too.
 */

import { CoachRpcError, type CoachApi } from "@/lib/coach-api";

/** The fields of `coach.session.state` this module reads. */
export interface SessionState {
  session_id: string | null;
  stage: string | null;
  revision: number;
  confirmed_steps: string[];
  safety_state: string;
  turns: { id: string; voice: string; content: string }[];
  candidates: { id: string; kind: string; value: string }[];
  ended: boolean;
}

export async function ensureOnboardingSession(
  api: CoachApi,
  sessionId: string,
): Promise<SessionState> {
  const existing = await read(api, sessionId);
  if (existing.session_id !== null) return existing;

  try {
    // A session that does not exist yet is at revision 0.
    await api.mutate("coach.session.start", {
      sessionId,
      revision: 0,
      params: {},
    });
  } catch (reason) {
    // A refusal here is not automatically a failure. React runs effects twice
    // in development, so two mounts can both read "missing" before either
    // writes; the loser is refused on revision, and that refusal means the
    // session it wanted now exists. The re-read below is what decides, so a
    // start that genuinely failed still surfaces.
    if (!(reason instanceof CoachRpcError)) throw reason;
  }

  // Re-read rather than assuming revision 1: the next mutation carries this
  // number back, and a guessed one is exactly what the server refuses.
  const started = await read(api, sessionId);
  if (started.session_id === null) {
    throw new Error("không tạo được phiên onboarding");
  }
  return started;
}

function read(api: CoachApi, sessionId: string): Promise<SessionState> {
  return api.call("coach.session.state", {
    session_id: sessionId,
  }) as Promise<SessionState>;
}
