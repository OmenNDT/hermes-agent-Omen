import { useCallback, useEffect, useState } from "react";

import { describeFailure, useCoachApi } from "@/lib/use-coach-today";
import type { JourneySession, JourneyTurn } from "./index";
import { Journey } from "./index";

export function JourneyRoute() {
  const api = useCoachApi();
  const [sessions, setSessions] = useState<JourneySession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [openTurns, setOpenTurns] = useState<JourneyTurn[] | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

  useEffect(() => {
    if (api === null) return;
    let cancelled = false;
    api
      .call("coach.journey")
      .then((answer) => {
        if (cancelled) return;
        setSessions((answer as { sessions: JourneySession[] }).sessions);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(describeFailure(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const onOpen = useCallback(
    (sessionId: string) => {
      if (api === null) return;
      // Cleared first, so the previous session's words never show under the
      // heading of a different one while this call is in flight.
      setOpenId(sessionId);
      setOpenTurns(null);
      setOpenError(null);
      api
        .call("coach.session.transcript", { session_id: sessionId })
        .then((answer) => {
          setOpenTurns((answer as { turns: JourneyTurn[] }).turns);
        })
        .catch((reason: unknown) => setOpenError(describeFailure(reason)));
    },
    [api],
  );

  const onClose = useCallback(() => {
    setOpenId(null);
    setOpenTurns(null);
    setOpenError(null);
  }, []);

  return (
    <Journey
      sessions={sessions ?? []}
      loading={api !== null && sessions === null && error === null}
      error={error}
      openId={openId}
      openTurns={openTurns}
      openError={openError}
      onOpen={onOpen}
      onClose={onClose}
    />
  );
}
