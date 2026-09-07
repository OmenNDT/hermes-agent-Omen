/**
 * The Check-in screen wired to the backend.
 *
 * Answering re-reads rather than patching locally: one answer closes this
 * check-in, may open the next, and may change or cancel the commitment, and a
 * screen that guessed at that would show a list the database disagrees with.
 */

import { useCallback, useEffect, useState } from "react";

import { describeFailure, useCoachApi } from "@/lib/use-coach-today";
import type { CheckInAction, PendingCheckIn } from "./index";
import { CheckIns } from "./index";

export function CheckInsRoute() {
  const api = useCoachApi();
  const [checkIns, setCheckIns] = useState<PendingCheckIn[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (api === null) return;
    let cancelled = false;
    api
      .call("coach.check_ins")
      .then((answer) => {
        if (cancelled) return;
        setCheckIns((answer as { check_ins: PendingCheckIn[] }).check_ins);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(describeFailure(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [api, attempt]);

  const onAnswer = useCallback(
    (
      checkInId: string,
      action: CheckInAction,
      payload: { editedCommitment?: string; rescheduledFor?: string },
    ) => {
      if (api === null) return;
      setBusy(checkInId);
      api
        .call("coach.check_in.answer", {
          command_id: crypto.randomUUID(),
          // The server refuses an answer with no trusted control behind it.
          ui_event_id: `btn-check-in-${action}`,
          check_in_id: checkInId,
          action,
          ...(payload.editedCommitment
            ? { edited_commitment: payload.editedCommitment }
            : {}),
          ...(payload.rescheduledFor
            ? { rescheduled_for: payload.rescheduledFor }
            : {}),
        })
        .then(() => setAttempt((count) => count + 1))
        .catch((reason: unknown) => setError(describeFailure(reason)))
        .finally(() => setBusy(null));
    },
    [api],
  );

  return (
    <CheckIns
      checkIns={checkIns ?? []}
      loading={api !== null && checkIns === null && error === null}
      error={error}
      busy={busy}
      onAnswer={onAnswer}
    />
  );
}
