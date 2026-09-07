/**
 * Home: where the Coachee is, in four lines or fewer.
 *
 * The proposal calls this destination, commitments, attention, learning. It is
 * deliberately not a feed. A coaching home screen that scrolls invites browsing
 * your own life; this one answers "what am I working towards, what did I say I
 * would do, what needs me today, what did I learn" and then stops.
 *
 * Every empty state says what to do next rather than showing a blank panel,
 * because the first run of this product is entirely empty states.
 */

import { day, describeTiming } from "@/lib/check-in-timing";
import type {
  TodayCheckIn,
  TodayGoal,
  TodayInsight,
} from "@/lib/use-coach-today";

export interface TodayProps {
  goals: TodayGoal[];
  checkIns: TodayCheckIn[];
  insight: TodayInsight | null;
  /** The unencrypted-storage disclosure, in the backend's own words. */
  disclosure: string | null;
  loading: boolean;
  error: string | null;
}

export function Today({
  goals,
  checkIns,
  insight,
  disclosure,
  loading,
  error,
}: TodayProps) {
  if (error) {
    return (
      <p role="alert" data-testid="today-error">
        {error}
      </p>
    );
  }
  if (loading) {
    return (
      <p role="status" data-testid="today-loading">
        Đang tải…
      </p>
    );
  }

  return (
    // The shell already renders "Hôm nay" as the page heading, so a second one
    // here would make a screen reader announce the same words twice. The label
    // carries the name instead.
    <section aria-label="Tổng quan hôm nay" data-testid="today">
      <h3>Đích đến</h3>
      {goals.length === 0 ? (
        <p data-testid="today-no-goals">
          Chưa có mục tiêu nào. Một phiên coaching là nơi mục tiêu xuất hiện —{" "}
          <a href="#/coach">mở một phiên</a>.
        </p>
      ) : (
        <ul data-testid="today-goals">
          {goals.map((goal) => (
            <li key={goal.id} data-testid={`today-goal-${goal.id}`}>
              <p>{goal.title}</p>
              {goal.target_date && (
                <p data-testid={`today-goal-date-${goal.id}`}>
                  Mốc: {goal.target_date}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Not "Cần bạn hôm nay": this panel carries commitments still coming as
          well as ones that have come due, and a heading that claimed all of
          them needed attention today would be false thirteen days out of
          fourteen. Each row says which it is. */}
      <h3>Cam kết bạn đang theo</h3>
      {checkIns.length === 0 ? (
        <p data-testid="today-no-check-ins">
          Chưa có cam kết nào đang theo dõi.
        </p>
      ) : (
        // The commitment's own words, not a bare timestamp: "2026-01-15" is
        // not something a Coachee can recognise as a promise they made.
        <ul data-testid="today-check-ins">
          {checkIns.map((checkIn) => (
            <li key={checkIn.id} data-testid={`today-check-in-${checkIn.id}`}>
              <p>{checkIn.action_text}</p>
              <p data-testid={`today-check-in-when-${checkIn.id}`}>
                {describeTiming(checkIn)} · {day(checkIn.scheduled_at)}
              </p>
            </li>
          ))}
        </ul>
      )}

      <h3>Điều bạn nhận ra gần đây</h3>
      {/* One, not a list. Home shows the latest learning, not a scroll of them. */}
      {insight === null ? (
        <p data-testid="today-no-insight">Chưa có ghi nhận nào.</p>
      ) : (
        <blockquote data-testid="today-insight">{insight.content}</blockquote>
      )}

      {disclosure && (
        <p role="note" data-testid="today-disclosure">
          {disclosure}
        </p>
      )}
    </section>
  );
}
