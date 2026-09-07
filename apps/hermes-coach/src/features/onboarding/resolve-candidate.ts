/**
 * Mint an intent, then consume it.
 *
 * Two round trips, not one, because the intent binds the exact action and the
 * exact edited text. Minting earlier — when the card first renders, say — would
 * let the payload change between mint and confirm, which is precisely what the
 * server refuses.
 */

import type { CoachApi } from "@/lib/coach-api";
import type { RecordAction } from "./record-confirmation";

export async function resolveCandidate(
  api: CoachApi,
  sessionId: string,
  candidateId: string,
  action: RecordAction,
  editedValue: string | null,
): Promise<void> {
  const intent = (await api.call("coach.candidate.intent", {
    session_id: sessionId,
    candidate_id: candidateId,
    action,
    edited_value: editedValue,
  })) as { intent_token: string };

  await api.call("coach.candidate.confirm", {
    // One command id per attempt: a retry after a refusal is a new attempt,
    // and reusing the id would be refused as a replay.
    command_id: crypto.randomUUID(),
    intent_token: intent.intent_token,
    candidate_id: candidateId,
    action,
    edited_value: editedValue,
  });
}
