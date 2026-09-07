/**
 * The coaching session screen.
 *
 * This component renders what the server said and nothing it inferred. It does
 * not decide that a stage advanced, that a gate opened, or that an answer
 * qualified — those are the server's judgements, and a screen that guessed them
 * would show the Coachee a step moving that the database never recorded.
 *
 * The composer is a single question at a time by construction: there is one
 * input, and it is disabled while a turn is in flight. Nothing here can send a
 * second message into an unanswered turn.
 */

import { useState } from "react";

import type { Candidate, SafetyState, Stage, Turn, Voice } from "@/store/session";
import { STAGE_LABELS } from "./stage-labels";
import type { ResumableSession } from "./route";
import { STAGES, coachingInterrupted } from "@/store/session";
import type { RecordAction } from "@/features/onboarding/record-confirmation";
import { RecordConfirmation } from "@/features/onboarding/record-confirmation";

/**
 * Who is speaking, said in words.
 *
 * Colour alone would not distinguish them, and the safety voice in particular
 * must never read as the Coach.
 */
const VOICE_LABELS: Record<Voice, string> = {
  coach: "Coach",
  coachee: "Bạn",
  product_ui: "Hệ thống",
  safety_system: "An toàn",
};

export interface CoachSessionProps {
  started: boolean;
  connected: boolean;
  stage: Stage | null;
  confirmedSteps: Stage[];
  safetyState: SafetyState;
  turns: Turn[];
  candidates: Candidate[];
  pendingTurnId: string | null;
  /** Review was confirmed; this session is finished. */
  ended: boolean;
  error: string | null;
  /** Something worth saying that is not a failure. */
  note: string | null;
  /** What the current step has still not covered, in the Coachee's words. */
  gaps: string[];
  /** An unfinished session the Coachee may return to. Offered, never assumed. */
  resumable: ResumableSession | null;
  onResume: () => void;
  onStart: (intention: string) => void;
  /** Resolves false when the turn did not land, so the answer can come back. */
  onSend: (message: string) => Promise<boolean>;
  onCancel: () => void;
  onResolveCandidate: (
    candidateId: string,
    action: RecordAction,
    editedValue: string | null,
  ) => Promise<void>;
}

export function CoachSession({
  started,
  connected,
  stage,
  confirmedSteps,
  safetyState,
  turns,
  candidates,
  pendingTurnId,
  ended,
  error,
  note,
  gaps,
  resumable,
  onResume,
  onStart,
  onSend,
  onCancel,
  onResolveCandidate,
}: CoachSessionProps) {
  const [intention, setIntention] = useState("");
  const [message, setMessage] = useState("");

  const busy = pendingTurnId !== null;

  // Safety replaces coaching rather than sitting as a banner above a live
  // composer: once the server has interrupted, there is no path to keep
  // coaching through it, so there is no composer to grey out.
  //
  // What is shown here is the Safety System's own message, written by the
  // server and read back out of the transcript. Nothing on this screen is
  // composed in the browser, and nothing the model generated for this turn is
  // displayed — the server never stored it.
  if (coachingInterrupted(safetyState)) {
    const spoken = [...turns]
      .reverse()
      .find((turn) => turn.voice === "safety_system");
    return (
      <section aria-labelledby="coach-urgent" data-testid="coach-urgent">
        <h2 id="coach-urgent">Phần coaching đã dừng</h2>
        <p data-testid="safety-voice">{VOICE_LABELS.safety_system}</p>
        <div role="alert" data-testid="safety-message">
          <p>
            {spoken
              ? spoken.content
              : "Phần coaching đã dừng vì lý do an toàn."}
          </p>
        </div>
        <p>Những gì bạn đã lưu vẫn còn nguyên và xem lại được bất cứ lúc nào.</p>

        <h3>Diễn tiến</h3>
        <ol data-testid="transcript">
          {turns.map((turn) => (
            <li key={turn.id} data-testid={`turn-${turn.id}`}>
              <span>{VOICE_LABELS[turn.voice] ?? turn.voice}</span>
              <p>{turn.content}</p>
            </li>
          ))}
        </ol>
      </section>
    );
  }

  // A finished session is not a session with the controls greyed out. The
  // Coachee confirmed Review; offering a composer here would invite them to
  // write into a record that is closed, and meet `session_ended` for it.
  if (ended) {
    return (
      <section aria-label="Phiên đã kết thúc" data-testid="coach-ended">
        <h2>Phiên đã khép lại</h2>
        <p>
          Bạn đã xác nhận bước Review, nên phiên này kết thúc ở đây. Những gì
          bạn đã lưu vẫn còn nguyên.
        </p>
        <p>
          <a href="#/goals">Xem mục tiêu</a> hoặc{" "}
          <a href="#/">quay về Hôm nay</a>.
        </p>
        <h3>Diễn tiến</h3>
        <ol data-testid="transcript">
          {turns.map((turn) => (
            <li key={turn.id} data-testid={`turn-${turn.id}`}>
              <span>{VOICE_LABELS[turn.voice] ?? turn.voice}</span>
              <p>{turn.content}</p>
            </li>
          ))}
        </ol>
      </section>
    );
  }

  if (!started) {
    return (
      <section aria-labelledby="coach-start" data-testid="coach-start">
        <h2 id="coach-start">Bắt đầu một phiên</h2>
        <p>
          Phiên đi theo sáu bước: Pre-Coaching → Goal → Reality → Options → Will
          → Review. Coach hỏi từng câu một, và bạn là người quyết định.
        </p>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onStart(intention.trim());
          }}
        >
          <label htmlFor="coach-intention">
            Bạn muốn dùng phiên này cho việc gì? (không bắt buộc)
          </label>
          <input
            id="coach-intention"
            value={intention}
            disabled={!connected}
            onChange={(event) => setIntention(event.target.value)}
          />
          <button type="submit" disabled={!connected}>
            Bắt đầu phiên
          </button>
        </form>

        {/* Offered on the start screen rather than adopted on load. Silently
            dropping someone into a half-finished conversation would be its own
            kind of wrong; leaving it unreachable was the worse one. */}
        {resumable && connected && (
          <div data-testid="coach-resume">
            <h3>Bạn còn một phiên chưa khép lại</h3>
            <p data-testid="coach-resume-detail">
              Mở ngày {resumable.started_at.slice(0, 10)}, dừng ở{" "}
              {STAGE_LABELS[resumable.stage] ?? resumable.stage}
              {resumable.intention ? ` — “${resumable.intention}”` : ""}.
            </p>
            <button type="button" onClick={onResume} data-testid="coach-resume-open">
              Tiếp tục phiên đó
            </button>
            <p>Hoặc bắt đầu một phiên mới ở trên; phiên cũ vẫn được giữ nguyên.</p>
          </div>
        )}

        {!connected && (
          <p role="status" data-testid="coach-offline">
            Chưa kết nối được backend, nên chưa mở được phiên mới.
          </p>
        )}
        {error && (
          <p role="alert" data-testid="coach-error">
            {error}
          </p>
        )}
      </section>
    );
  }

  const confirmed = new Set(confirmedSteps);
  const latestCoachTurn = [...turns]
    .reverse()
    .find((turn) => turn.voice === "coach");

  return (
    <section aria-labelledby="coach-session" data-testid="coach-session">
      <h2 id="coach-session">Phiên đang diễn ra</h2>

      <ol aria-label="Sáu bước" data-testid="stage-rail">
        {STAGES.map((step) => (
          <li
            key={step}
            aria-current={step === stage ? "step" : undefined}
            data-testid={`stage-${step}`}
          >
            {STAGE_LABELS[step]}
            {confirmed.has(step) && <span> · đã xác nhận</span>}
          </li>
        ))}
      </ol>

      {/* The current question, announced. A Coachee using a screen reader must
          not have to hunt the transcript for the thing they are being asked. */}
      <div role="status" aria-live="polite" data-testid="current-question">
        {latestCoachTurn ? (
          <p>{latestCoachTurn.content}</p>
        ) : (
          <p>Coach chưa hỏi gì. Hãy nói điều bạn đang mang theo.</p>
        )}
      </div>

      <h3>Diễn tiến</h3>
      <ol data-testid="transcript">
        {turns.map((turn) => (
          <li key={turn.id} data-testid={`turn-${turn.id}`}>
            <span>{VOICE_LABELS[turn.voice] ?? turn.voice}</span>
            <p>{turn.content}</p>
          </li>
        ))}
      </ol>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          const text = message.trim();
          if (!text) return;
          // Cleared optimistically so the composer looks sent, and put back
          // verbatim if it was not. A Coachee who has just written something
          // difficult should never be asked to write it again because the
          // model returned a question that failed validation.
          setMessage("");
          void onSend(text).then((landed) => {
            if (!landed) setMessage(text);
          });
        }}
      >
        <label htmlFor="coach-message">Trả lời của bạn</label>
        <textarea
          id="coach-message"
          value={message}
          rows={4}
          disabled={busy || !connected}
          onChange={(event) => setMessage(event.target.value)}
        />
        <button type="submit" disabled={busy || !connected}>
          Gửi
        </button>
        {/* Cancel is offered only while a turn is in flight, and cancels that
            turn alone — never the session. */}
        {busy && (
          <button type="button" onClick={onCancel} data-testid="cancel-turn">
            Huỷ lượt này
          </button>
        )}
      </form>

      {/* Named, not enforced. The six steps rested entirely on the closing
          gate, with nothing checking a step had content in it — a live run had
          the Coach move to Reality and immediately ask an Options question, and
          nothing objected. Saying what is still uncovered is what lets a
          Coachee see that happening rather than only feel it. */}
      {gaps.length > 0 && (
        <p role="status" data-testid="coach-gaps">
          Bước này chưa nói tới {gaps.join(", ")}.
        </p>
      )}
      {safetyState === "sensitive" && (
        // Stated, not hidden: the server raised the state and coaching
        // continues, and the Coachee is owed both halves of that.
        <p role="status" data-testid="safety-sensitive">
          Coach đang đi chậm lại ở phần này. Bạn có thể dừng bất cứ lúc nào.
        </p>
      )}
      {busy && (
        <p role="status" data-testid="coach-thinking">
          Coach đang nghĩ…
        </p>
      )}
      {/* Announced, not silent. A Coachee who agreed and saw nothing happen is
          owed the reason — status rather than alert, because nothing failed. */}
      {note && (
        <p role="status" data-testid="coach-note">
          {note}
        </p>
      )}
      {error && (
        <p role="alert" data-testid="coach-error">
          {error}
        </p>
      )}

      <h3>Mục cần xác nhận</h3>
      <RecordConfirmation
        candidates={candidates}
        onResolve={onResolveCandidate}
      />
    </section>
  );
}
