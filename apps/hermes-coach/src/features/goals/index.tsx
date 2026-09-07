/**
 * Every goal the Coachee has confirmed.
 *
 * Read-only on purpose. A goal becomes official by being confirmed one card at
 * a time inside a session; an edit control here would be a second, quieter path
 * to changing a record the Coachee already signed off, with none of that
 * evidence attached.
 */

import type { TodayGoal } from "@/lib/use-coach-today";

const STATUS_LABELS: Record<string, string> = {
  active: "Đang theo",
  achieved: "Đã đạt",
  abandoned: "Đã bỏ",
  paused: "Tạm dừng",
};

export interface GoalsProps {
  goals: TodayGoal[];
  loading: boolean;
  error: string | null;
}

export function Goals({ goals, loading, error }: GoalsProps) {
  if (error) {
    return (
      <p role="alert" data-testid="goals-error">
        {error}
      </p>
    );
  }
  if (loading) {
    return (
      <p role="status" data-testid="goals-loading">
        Đang tải…
      </p>
    );
  }
  if (goals.length === 0) {
    return (
      <section aria-label="Mục tiêu đã xác nhận" data-testid="goals-empty">
        <p>
          Chưa có mục tiêu nào được xác nhận. Mục tiêu sinh ra trong một phiên
          coaching và chỉ thành của bạn khi bạn bấm Lưu —{" "}
          <a href="#/coach">mở một phiên</a>.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Mục tiêu đã xác nhận" data-testid="goals">
      <p>{goals.length} mục tiêu bạn đã xác nhận.</p>
      <ul data-testid="goals-list">
        {goals.map((goal) => (
          <li key={goal.id} data-testid={`goal-${goal.id}`}>
            <p>{goal.title}</p>
            <p data-testid={`goal-status-${goal.id}`}>
              {STATUS_LABELS[goal.status] ?? goal.status}
              {goal.target_date ? ` · mốc ${goal.target_date}` : ""}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
