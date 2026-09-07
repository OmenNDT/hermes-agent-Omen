/**
 * Coming back to a commitment.
 *
 * The four choices are deliberately not "done" and "not done". A commitment the
 * Coachee did not keep is information about the commitment, not a verdict on
 * them, so the question this screen asks is what the commitment should now be —
 * which is what a coach would actually ask.
 *
 * Nothing here decides anything. The server closes this check-in, opens the
 * next one and moves the commitment; the screen shows what came back.
 */

import { useState } from "react";

import { day, describeTiming } from "@/lib/check-in-timing";

export type CheckInAction = "keep" | "edit" | "reschedule" | "cancel";

export interface PendingCheckIn {
  id: string;
  commitment_id: string;
  action_text: string;
  goal_id: string;
  scheduled_at: string;
  due_at: string | null;
  due: boolean;
  days_until: number | null;
}

export interface CheckInsProps {
  checkIns: PendingCheckIn[];
  loading: boolean;
  error: string | null;
  busy: string | null;
  onAnswer: (
    checkInId: string,
    action: CheckInAction,
    payload: { editedCommitment?: string; rescheduledFor?: string },
  ) => void;
}

export function CheckIns({
  checkIns,
  loading,
  error,
  busy,
  onAnswer,
}: CheckInsProps) {
  // Which card has opened its edit or reschedule form, and what is typed in it.
  const [open, setOpen] = useState<{ id: string; action: CheckInAction } | null>(
    null,
  );
  const [draft, setDraft] = useState("");

  if (error) {
    return (
      <p role="alert" data-testid="check-ins-error">
        {error}
      </p>
    );
  }
  if (loading) {
    return (
      <p role="status" data-testid="check-ins-loading">
        Đang tải…
      </p>
    );
  }
  if (checkIns.length === 0) {
    return (
      <section aria-label="Check-in" data-testid="check-ins-empty">
        <p>
          Chưa có check-in nào đang chờ. Check-in xuất hiện khi bạn xác nhận một
          cam kết trong phiên — <a href="#/coach">mở một phiên</a>.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Check-in đang chờ" data-testid="check-ins">
      {/* Counted separately, because "3 cam kết đang chờ" over two that are
          not due yet and one that is overdue tells the Coachee nothing about
          which needs them. */}
      <p data-testid="check-ins-summary">
        {checkIns.filter((one) => one.due).length} cam kết đã tới hẹn,{" "}
        {checkIns.filter((one) => !one.due).length} đang tới.
      </p>
      <ul data-testid="check-ins-list">
        {checkIns.map((checkIn) => {
          const working = busy === checkIn.id;
          const form = open?.id === checkIn.id ? open.action : null;
          return (
            <li key={checkIn.id} data-testid={`check-in-${checkIn.id}`}>
              <p data-testid={`check-in-text-${checkIn.id}`}>
                {checkIn.action_text}
              </p>
              <p data-testid={`check-in-when-${checkIn.id}`}>
                {describeTiming(checkIn)} · {day(checkIn.scheduled_at)}
              </p>

              {form === null && (
                <div>
                  <button
                    type="button"
                    disabled={working}
                    onClick={() => onAnswer(checkIn.id, "keep", {})}
                    data-testid={`keep-${checkIn.id}`}
                  >
                    Giữ nguyên
                  </button>
                  <button
                    type="button"
                    disabled={working}
                    onClick={() => {
                      setDraft(checkIn.action_text);
                      setOpen({ id: checkIn.id, action: "edit" });
                    }}
                    data-testid={`edit-${checkIn.id}`}
                  >
                    Sửa lại
                  </button>
                  <button
                    type="button"
                    disabled={working}
                    onClick={() => {
                      setDraft(day(checkIn.scheduled_at));
                      setOpen({ id: checkIn.id, action: "reschedule" });
                    }}
                    data-testid={`reschedule-${checkIn.id}`}
                  >
                    Hẹn lại
                  </button>
                  <button
                    type="button"
                    disabled={working}
                    onClick={() => onAnswer(checkIn.id, "cancel", {})}
                    data-testid={`cancel-${checkIn.id}`}
                  >
                    Bỏ cam kết này
                  </button>
                </div>
              )}

              {form !== null && (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    const text = draft.trim();
                    if (!text) return;
                    onAnswer(
                      checkIn.id,
                      form,
                      form === "edit"
                        ? { editedCommitment: text }
                        : // The server stores instants; a date input gives a day.
                          { rescheduledFor: `${text}T00:00:00Z` },
                    );
                    setOpen(null);
                  }}
                >
                  <label htmlFor={`draft-${checkIn.id}`}>
                    {form === "edit" ? "Cam kết mới" : "Hẹn lại vào ngày"}
                  </label>
                  <input
                    id={`draft-${checkIn.id}`}
                    type={form === "edit" ? "text" : "date"}
                    value={draft}
                    disabled={working}
                    onChange={(event) => setDraft(event.target.value)}
                  />
                  <button type="submit" disabled={working}>
                    Lưu
                  </button>
                  <button
                    type="button"
                    disabled={working}
                    onClick={() => setOpen(null)}
                    data-testid={`dismiss-${checkIn.id}`}
                  >
                    Thôi
                  </button>
                </form>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
