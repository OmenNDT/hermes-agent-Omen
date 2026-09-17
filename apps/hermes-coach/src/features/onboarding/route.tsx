/**
 * Onboarding wired to the backend.
 *
 * The component itself takes callbacks and knows nothing about RPC, so it stays
 * testable without a socket; this module is the only place the two meet.
 */

import { useEffect, useState } from "react";

import type { CoachApi } from "@/lib/coach-api";
import { coachApi } from "@/lib/connection";
import { ensureOnboardingSession } from "./ensure-session";
import { Onboarding } from "./index";
import type { CandidateCard, RecordAction } from "./record-confirmation";
import { resolveCandidate } from "./resolve-candidate";
import type { ConsentDecision } from "./steps";

/**
 * Onboarding runs inside one coaching session, so the records it confirms
 * belong to it.
 *
 * The id is fixed rather than minted per visit, and that is what makes a reload
 * rejoin the same session instead of stranding its records under an id nobody
 * holds any more. Onboarding happens once and has no "which one?" to resolve,
 * so it needs none of the resume offer the coaching screen presents.
 */
const ONBOARDING_SESSION = "onboarding";

/** Where the first goal is actually made. */
const COACH_PATH = "/coach";

export function OnboardingRoute() {
  // Resolved once during the first render rather than inside the effect: not
  // being connected is knowable synchronously, and setting state for it in an
  // effect costs an extra render pass for nothing.
  const [api] = useState<CoachApi | Error>(() => {
    try {
      return coachApi();
    } catch (reason) {
      return reason as Error;
    }
  });
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CandidateCard[]>([]);

  useEffect(() => {
    if (api instanceof Error) return;
    let cancelled = false;
    Promise.all([
      // The disclosure text comes from the backend so the browser and the
      // launcher cannot drift into telling the Coachee different things.
      api.call("coach.today"),
      // Nothing else creates it, and everything below writes into it. Started
      // here rather than on the first confirmation so a Coachee who never
      // reaches the records step still leaves a session behind to return to.
      ensureOnboardingSession(api, ONBOARDING_SESSION),
    ])
      .then(([today, state]) => {
        if (cancelled) return;
        setNote((today as { disclosure: { note: string } }).disclosure.note);
        // Seeded from the read the ensure already did, rather than a third
        // round trip that could disagree with it.
        setCandidates(state.candidates);
      })
      .catch((reason: Error) => !cancelled && setError(reason.message));
    return () => {
      cancelled = true;
    };
  }, [api]);

  if (api instanceof Error) return <p role="alert">{api.message}</p>;
  if (error) return <p role="alert">{error}</p>;
  if (note === null) return <p role="status">Đang tải…</p>;

  // The narrowing above does not reach the hoisted declarations below, so the
  // connected client is captured here where it is known to be one.
  const client: CoachApi = api;

  async function refreshCandidates() {
    const state = (await client.call("coach.session.state", {
      session_id: ONBOARDING_SESSION,
    })) as { candidates: CandidateCard[] };
    setCandidates(state.candidates);
  }

  async function resolve(
    candidateId: string,
    action: RecordAction,
    editedValue: string | null,
  ) {
    await resolveCandidate(
      client,
      ONBOARDING_SESSION,
      candidateId,
      action,
      editedValue,
    );
    // Re-read rather than removing the card locally: the server is what decides
    // a candidate is resolved, and a local guess could disagree with it.
    await refreshCandidates();
  }

  return (
    <Onboarding
      onConsent={recordConsent}
      disclosureNote={note}
      candidates={candidates}
      onResolveCandidate={resolve}
      onFinish={() => void refreshCandidates()}
      onCreateFirstGoal={() => {
        // A goal is never created by a direct command: it is produced inside a
        // coaching turn as a candidate and confirmed there. So this hands over
        // to the session screen rather than writing anything itself.
        window.location.hash = `#${COACH_PATH}`;
      }}
    />
  );
}

async function recordConsent(
  consentType: string,
  uiAction: "confirm" | "decline",
  controlId: string,
): Promise<ConsentDecision> {
  const answer = (await coachApi().call("coach.consent.record", {
    event_id: crypto.randomUUID(),
    consent_type: consentType,
    scope: {},
    ui_action: uiAction,
    control_id: controlId,
  })) as { decision: ConsentDecision };
  // The server's decision, not the button that was clicked.
  return answer.decision;
}
