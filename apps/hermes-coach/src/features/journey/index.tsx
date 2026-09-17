/**
 * Every session the Coachee has held.
 *
 * Deliberately not an activity log. A list of dates says how often someone
 * showed up, which is a metric about them; what makes a history worth opening
 * is what each session left behind — the goal it produced, the thing they
 * realised, the promise they made.
 *
 * A session that produced nothing says so plainly. It did not fail: sitting
 * with something and reaching no conclusion is a real hour of coaching, and a
 * screen that hid those would quietly teach the Coachee that only productive
 * sessions count.
 */

import { STAGE_LABELS } from "@/features/coach/stage-labels";
import type { Stage, Voice } from "@/store/session";

export interface JourneySession {
  id: string;
  started_at: string;
  ended_at: string | null;
  intention: string | null;
  stage: Stage;
  ended: boolean;
  safety_state: string;
  produced: { goals: number; insights: number; commitments: number };
  /** Live transcript lines. Zero once the retention window has aged them out. */
  messages: number;
  /** Lines ever written. Separates "nothing was said" from "the words are gone". */
  messages_ever: number;
}

export interface JourneyTurn {
  id: string;
  voice: Voice;
  content: string;
}

export interface JourneyProps {
  sessions: JourneySession[];
  loading: boolean;
  error: string | null;
  /** The session whose transcript is open, and its lines once they arrive. */
  openId: string | null;
  openTurns: JourneyTurn[] | null;
  openError: string | null;
  onOpen: (sessionId: string) => void;
  onClose: () => void;
  /** Print the open session, which is how the Coachee saves it as a PDF. */
  onExport?: (sessionId: string) => void;
  /** Set while the export is being fetched, so the button cannot be double-fired. */
  exporting?: boolean;
  exportError?: string | null;
}

/**
 * Who said it, in words.
 *
 * The Safety System must stay distinguishable from the Coach months later,
 * exactly as it was during the session — a safety message that reads as
 * coaching advice is the one confusion this product cannot afford.
 */
const VOICE_LABELS: Record<Voice, string> = {
  coach: "Coach",
  coachee: "Bạn",
  product_ui: "Hệ thống",
  safety_system: "An toàn",
};

function day(timestamp: string): string {
  return timestamp.slice(0, 10);
}

/** "1 mục tiêu · 2 nhận thức", omitting whatever was not produced. */
function describeProduced(produced: JourneySession["produced"]): string {
  const parts = [
    produced.goals && `${produced.goals} mục tiêu`,
    produced.insights && `${produced.insights} nhận thức`,
    produced.commitments && `${produced.commitments} cam kết`,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "Chưa lưu lại gì";
}

export function Journey({
  sessions,
  loading,
  error,
  openId,
  openTurns,
  openError,
  onOpen,
  onClose,
  onExport,
  exporting = false,
  exportError = null,
}: JourneyProps) {
  if (error) {
    return (
      <p role="alert" data-testid="journey-error">
        {error}
      </p>
    );
  }
  if (loading) {
    return (
      <p role="status" data-testid="journey-loading">
        Đang tải…
      </p>
    );
  }
  if (sessions.length === 0) {
    return (
      <section aria-label="Hành trình" data-testid="journey-empty">
        <p>
          Chưa có phiên nào. Hành trình của bạn bắt đầu từ phiên đầu tiên —{" "}
          <a href="#/coach">mở một phiên</a>.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Hành trình" data-testid="journey">
      <p>{sessions.length} phiên bạn đã đi qua.</p>
      <ol data-testid="journey-list">
        {sessions.map((session) => (
          <li key={session.id} data-testid={`journey-${session.id}`}>
            <p data-testid={`journey-when-${session.id}`}>
              {day(session.started_at)}
              {session.ended ? "" : " · chưa khép lại"}
            </p>
            {session.intention && (
              <p data-testid={`journey-intention-${session.id}`}>
                “{session.intention}”
              </p>
            )}
            <p data-testid={`journey-stage-${session.id}`}>
              {session.ended
                ? "Đi hết sáu bước"
                : `Dừng ở ${STAGE_LABELS[session.stage] ?? session.stage}`}
            </p>
            <p data-testid={`journey-produced-${session.id}`}>
              {describeProduced(session.produced)}
            </p>
            {/* Said, not hidden — but only when it is true. The first live run
                of this screen reported three sessions as having lost their
                contents; all three had simply been opened and abandoned before
                the first turn, three days earlier, well inside a ninety-day
                window. A false alarm about someone's own data is worse than
                saying nothing, so this needs both counts to disagree. */}
            {session.messages === 0 && session.messages_ever > 0 && (
              <p data-testid={`journey-no-transcript-${session.id}`}>
                Nội dung trò chuyện đã hết hạn lưu và không còn đọc lại được.
              </p>
            )}

            {/* The product stopped deleting transcripts and said so on the
                Privacy screen — while no screen could open one. Keeping
                someone's words somewhere they can never read them carries the
                whole privacy cost of storage and returns none of its value. */}
            {session.messages > 0 &&
              (openId === session.id ? (
                <div>
                  <button
                    type="button"
                    onClick={onClose}
                    data-testid={`journey-close-${session.id}`}
                  >
                    Đóng lại
                  </button>
                  {onExport && openTurns !== null && openTurns.length > 0 && (
                    <button
                      type="button"
                      disabled={exporting}
                      onClick={() => onExport(session.id)}
                      data-testid={`journey-export-${session.id}`}
                    >
                      {exporting ? "Đang chuẩn bị…" : "Xuất PDF"}
                    </button>
                  )}
                  {exportError && (
                    <p role="alert" data-testid="journey-export-error">
                      {exportError}
                    </p>
                  )}
                  {openError && (
                    <p role="alert" data-testid="journey-transcript-error">
                      {openError}
                    </p>
                  )}
                  {openTurns === null && !openError && (
                    <p role="status" data-testid="journey-transcript-loading">
                      Đang mở…
                    </p>
                  )}
                  {openTurns !== null && (
                    <ol data-testid={`journey-transcript-${session.id}`}>
                      {openTurns.map((turn) => (
                        <li key={turn.id} data-testid={`journey-turn-${turn.id}`}>
                          <span>{VOICE_LABELS[turn.voice] ?? turn.voice}</span>
                          <p>{turn.content}</p>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => onOpen(session.id)}
                  data-testid={`journey-open-${session.id}`}
                >
                  Đọc lại {session.messages} lượt
                </button>
              ))}
          </li>
        ))}
      </ol>
    </section>
  );
}
