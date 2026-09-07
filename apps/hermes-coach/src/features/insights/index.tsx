/**
 * Everything the Coachee has confirmed learning about themselves.
 *
 * Home shows the latest one because a home screen should not be a scroll; this
 * is the place the whole set lives. Read-only, and phrased as theirs: each line
 * is a sentence they wrote and then chose to keep.
 */

export interface Insight {
  id: string;
  content: string;
  topic: string | null;
  confirmed_at: string | null;
}

export interface InsightsProps {
  insights: Insight[];
  loading: boolean;
  error: string | null;
}

export function Insights({ insights, loading, error }: InsightsProps) {
  if (error) {
    return (
      <p role="alert" data-testid="insights-error">
        {error}
      </p>
    );
  }
  if (loading) {
    return (
      <p role="status" data-testid="insights-loading">
        Đang tải…
      </p>
    );
  }
  if (insights.length === 0) {
    return (
      <section aria-label="Nhận thức đã lưu" data-testid="insights-empty">
        <p>
          Chưa có nhận thức nào được lưu. Chúng xuất hiện khi bạn tự nói ra điều
          mình nhận thấy trong một phiên, và chỉ được giữ khi bạn bấm Lưu —{" "}
          <a href="#/coach">mở một phiên</a>.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Nhận thức đã lưu" data-testid="insights">
      <p>{insights.length} điều bạn đã ghi lại.</p>
      <ul data-testid="insights-list">
        {insights.map((insight) => (
          <li key={insight.id} data-testid={`insight-${insight.id}`}>
            <blockquote>{insight.content}</blockquote>
            {insight.confirmed_at && (
              <p data-testid={`insight-date-${insight.id}`}>
                Lưu ngày {insight.confirmed_at.slice(0, 10)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
