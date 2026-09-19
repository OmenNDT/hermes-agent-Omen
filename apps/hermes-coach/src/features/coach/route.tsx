/**
 * The coaching session wired to the backend.
 *
 * The component above knows nothing about RPC; this module is the only place
 * the two meet, the same split onboarding uses.
 *
 * Every mutation carries the revision the server last reported, never one this
 * module incremented. After a command lands, the session is re-read rather than
 * patched locally: the server is what decides the stage, the gates and which
 * candidates are still pending, and a local guess could disagree with it.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useStore } from "@nanostores/react";

import type { CoachApi } from "@/lib/coach-api";
import { CoachRpcError } from "@/lib/coach-api";
import { coachApi } from "@/lib/connection";
import type { RecordAction } from "@/features/onboarding/record-confirmation";
import { resolveCandidate } from "@/features/onboarding/resolve-candidate";
import {
  $connection,
  $session,
  applyServerSnapshot,
  clearPendingTurn,
  markTurnPending,
  resetSession,
} from "@/store/session";
import type { Candidate, SafetyState, Stage, Turn } from "@/store/session";
import { CoachSession } from "./index";

/** What `coach.session.open` answers: enough to offer, not to render. */
export interface ResumableSession {
  session_id: string;
  started_at: string;
  intention: string | null;
  stage: Stage;
}

/** What the server answers for `coach.session.state`. */
interface SessionStatePayload {
  session_id: string | null;
  stage: Stage | null;
  revision: number;
  confirmed_steps: Stage[];
  safety_state: SafetyState;
  turns: Turn[];
  candidates: Candidate[];
  ended: boolean;
}

/**
 * A message for a code the Coachee can act on.
 *
 * Only codes whose remedy is outside the app are translated here. Anything else
 * keeps the server's own message, because inventing a friendlier sentence for a
 * failure we do not understand would only hide it.
 */
const MESSAGE_FOR_CODE: Record<string, string> = {
  provider_not_configured:
    "Chưa cấu hình mô hình cho Coach. Dữ liệu đã lưu vẫn xem được; chạy `claude auth login` rồi khởi động lại Coach để hỏi đáp.",
  consent_withdrawn:
    "Bạn chưa đồng ý gửi dữ liệu tới mô hình, nên phần hỏi đáp chưa dùng được. Mở lại phần Bắt đầu để quyết định.",
  stale_revision:
    "Phiên đã thay đổi ở nơi khác. Trang vừa đọc lại trạng thái mới nhất, mời bạn thử lại.",
};

function describe(reason: unknown): string {
  if (reason instanceof CoachRpcError) {
    return MESSAGE_FOR_CODE[reason.code] ?? `${reason.code}: ${reason.message}`;
  }
  return (reason as Error).message;
}

/**
 * Shown when a plain "Đồng ý" answered no open question.
 *
 * It names the situation without blaming the Coachee for it: their words were
 * fine, there was simply nothing waiting for them.
 */
const UNMATCHED_YES_NOTE =
  "Bạn vừa đồng ý, nhưng lúc này chưa có câu chốt bước nào đang mở nên bước " +
  "chưa đóng. Không mất gì cả — cứ tiếp tục, Coach sẽ hỏi câu xác nhận khi " +
  "bước này đủ.";

export function CoachSessionRoute() {
  const connection = useStore($connection);
  const session = useStore($session);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [resumable, setResumable] = useState<ResumableSession | null>(null);
  const [gaps, setGaps] = useState<string[]>([]);
  const [attempt, setAttempt] = useState(0);

  // Derived during render from the connection state, not stored in an effect:
  // the shell renders before `main.tsx` finishes connecting, so the client has
  // to be re-resolved when the connection comes up rather than grabbed once at
  // mount and kept broken for the life of the page.
  const api = useMemo<CoachApi | null>(() => {
    if (connection !== "online") return null;
    try {
      return coachApi();
    } catch {
      return null;
    }
  }, [connection]);

  const refresh = useCallback(
    async (client: CoachApi, sessionId: string) => {
      const state = (await client.call("coach.session.state", {
        session_id: sessionId,
      })) as SessionStatePayload;
      applyServerSnapshot({
        sessionId: state.session_id,
        stage: state.stage,
        revision: state.revision,
        confirmedSteps: state.confirmed_steps,
        safetyState: state.safety_state,
        turns: state.turns,
        candidates: state.candidates,
        ended: state.ended,
      });
    },
    [],
  );

  // A reload still does not silently adopt a half-finished session — that was a
  // deliberate choice and it stands. But it used to strand one: the id lived
  // only here in memory, so a reload, or a trip to Goals and back, put the
  // session permanently out of reach with every word still in the database.
  // Thirteen of sixteen sessions in a real profile read "chưa khép lại", and
  // most had been lost rather than abandoned.
  //
  // So it is offered, not assumed. The Coachee decides whether to go back.
  useEffect(() => resetSession, []);

  useEffect(() => {
    if (api === null) return;
    let cancelled = false;
    api
      .call("coach.session.open")
      .then((answer) => {
        if (cancelled) return;
        setResumable((answer as { session: ResumableSession | null }).session);
      })
      .catch(() => {
        // A failed look-up must not block starting a new session: the offer is
        // a convenience, and the start screen has to work without it.
        if (!cancelled) setResumable(null);
      });
    return () => {
      cancelled = true;
    };
  }, [api, attempt]);

  const resume = useCallback(async () => {
    if (!api || !resumable) return;
    setError(null);
    try {
      await refresh(api, resumable.session_id);
    } catch (reason) {
      setError(describe(reason));
    }
  }, [api, resumable, refresh]);

  async function start(intention: string) {
    if (!api) return;
    setError(null);
    const sessionId = crypto.randomUUID();
    try {
      // A session that does not exist yet is at revision 0.
      await api.mutate("coach.session.start", {
        sessionId,
        revision: 0,
        params: intention ? { intention } : {},
      });
      setResumable(null);
      await refresh(api, sessionId);
      setAttempt((count) => count + 1);
    } catch (reason) {
      setError(describe(reason));
    }
  }

  async function send(userMessage: string): Promise<boolean> {
    const sessionId = session.sessionId;
    if (!api || !sessionId) return false;
    setError(null);
    const turnId = crypto.randomUUID();
    markTurnPending(turnId);
    let landed = false;
    try {
      const answer = (await api.mutate("coach.turn", {
        sessionId,
        revision: session.revision,
        params: { turn_id: turnId, user_message: userMessage },
      })) as { unmatched_yes?: boolean; stage_gaps?: string[] };
      landed = true;
      // What this step has still not covered. Shown, not enforced: the server
      // does not refuse a gate on it yet, and pretending otherwise here would
      // be a second opinion the database does not hold.
      setGaps(answer?.stage_gaps ?? []);
      // The Coachee agreed and nothing moved. That is not an error and nothing
      // was lost, but from where they sit they said yes to silence — twice in
      // one live session, because the Coach had closed with a phrasing that
      // does not count as a closing question. Left unsaid, the only conclusion
      // available to them is that the product is broken.
      setNote(answer?.unmatched_yes ? UNMATCHED_YES_NOTE : null);
    } catch (reason) {
      setError(describe(reason));
    } finally {
      clearPendingTurn();
      // Re-read even after a failure: a rejected turn wrote nothing, and the
      // screen must show what the session actually is rather than what the
      // attempt hoped it would become.
      try {
        await refresh(api, sessionId);
      } catch (reason) {
        setError(describe(reason));
      }
    }
    // A refused turn wrote nothing at all — not the message, not the gate — so
    // the session is exactly where it was and the same answer can be sent
    // again. Saying so is what lets the composer hand it back.
    return landed;
  }

  async function cancel() {
    const { sessionId, pendingTurnId } = session;
    if (!api || !sessionId || !pendingTurnId) return;
    try {
      await api.cancel(sessionId, pendingTurnId);
    } catch (reason) {
      setError(describe(reason));
    }
  }

  async function resolve(
    candidateId: string,
    action: RecordAction,
    editedValue: string | null,
  ) {
    const sessionId = session.sessionId;
    if (!api || !sessionId) return;
    await resolveCandidate(api, sessionId, candidateId, action, editedValue);
    await refresh(api, sessionId);
  }

  return (
    <CoachSession
      started={session.sessionId !== null}
      connected={api !== null}
      stage={session.stage}
      confirmedSteps={session.confirmedSteps}
      safetyState={session.safetyState}
      turns={session.turns}
      candidates={session.candidates}
      pendingTurnId={session.pendingTurnId}
      ended={session.ended}
      error={error}
      note={note}
      gaps={gaps}
      resumable={resumable}
      onResume={resume}
      onStart={(intention) => void start(intention)}
      onSend={send}
      onCancel={() => void cancel()}
      onResolveCandidate={resolve}
    />
  );
}
