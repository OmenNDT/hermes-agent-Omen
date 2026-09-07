/**
 * What this app is holding, and what the Coachee has agreed to.
 *
 * The product's privacy promise is not a page of policy text: it is that a
 * withdrawal takes effect on the very next scoped write or model egress. So
 * this screen is two things and no more — the disclosure in the backend's own
 * words, and the standing decisions with a way to take one back.
 *
 * Withdrawal is offered per scope rather than as one master switch, because the
 * two are genuinely different: local storage is what the app keeps, model
 * egress is what leaves the machine. Collapsing them would force a Coachee who
 * only wanted to stop sending data to also give up their own records.
 *
 * Taking the data out and deleting it live here too. Both had a service behind
 * them for months and no way to reach it, so this screen could describe what
 * the Coachee owned without offering them a single thing to do about it.
 */

export type Decision = "granted" | "declined" | "withdrawn" | null;

export interface ConsentLine {
  consentType: string;
  label: string;
  meaning: string;
  decision: Decision;
}

export interface TrashItem {
  entity_type: string;
  entity_id: string;
  deleted_at: string;
  purge_after: string;
}

export interface PrivacyProps {
  disclosure: string | null;
  encryptedAtRest: boolean | null;
  consents: ConsentLine[];
  storedCounts: { goals: number; insights: number } | null;
  trash: TrashItem[];
  loading: boolean;
  error: string | null;
  busy: string | null;
  onWithdraw: (consentType: string) => void;
  onExport: (format: "json" | "markdown") => void;
  onRestore: (entityType: string, entityId: string) => void;
  onPurge: (entityType: string, entityId: string) => void;
}

const ENTITY_LABELS: Record<string, string> = {
  goal: "Mục tiêu",
  insight: "Nhận thức",
  commitment: "Cam kết",
  memory_item: "Ghi nhớ",
  coaching_session: "Phiên",
  candidate_record: "Mục chờ xác nhận",
};

const DECISION_LABELS: Record<string, string> = {
  granted: "Đã đồng ý",
  declined: "Đã từ chối",
  withdrawn: "Đã rút",
};

export function Privacy({
  disclosure,
  encryptedAtRest,
  consents,
  storedCounts,
  trash,
  loading,
  error,
  busy,
  onWithdraw,
  onExport,
  onRestore,
  onPurge,
}: PrivacyProps) {
  if (error) {
    return (
      <p role="alert" data-testid="privacy-error">
        {error}
      </p>
    );
  }
  if (loading) {
    return (
      <p role="status" data-testid="privacy-loading">
        Đang tải…
      </p>
    );
  }

  return (
    <section aria-label="Quyền riêng tư" data-testid="privacy">
      <h3>Dữ liệu của bạn nằm ở đâu</h3>
      {disclosure && <p data-testid="privacy-disclosure">{disclosure}</p>}
      {encryptedAtRest === false && (
        <p data-testid="privacy-not-encrypted">
          Bản MVP này <strong>không mã hoá</strong> dữ liệu khi lưu. Hãy cân
          nhắc điều đó trước khi chia sẻ những chuyện nhạy cảm nhất.
        </p>
      )}
      {/* Said here rather than in the versioned disclosure, which states the
          encryption fact and should not drift. A Coachee deciding what to say
          in a session is owed the knowledge that the words stay until they
          remove them — the product keeps them on purpose now, and a retention
          promise nobody made is still a promise they might assume. */}
      <p data-testid="privacy-retention">
        Nội dung trò chuyện được giữ lại cho tới khi bạn tự xoá. Mục tiêu, nhận
        thức và cam kết cũng vậy.
      </p>
      {storedCounts && (
        <p data-testid="privacy-counts">
          Đang lưu: {storedCounts.goals} mục tiêu, {storedCounts.insights} nhận
          thức.
        </p>
      )}

      <h3>Bạn đã đồng ý những gì</h3>
      <ul data-testid="privacy-consents">
        {consents.map((consent) => (
          <li
            key={consent.consentType}
            data-testid={`consent-${consent.consentType}`}
          >
            <p>{consent.label}</p>
            <p data-testid={`consent-meaning-${consent.consentType}`}>
              {consent.meaning}
            </p>
            <p data-testid={`consent-decision-${consent.consentType}`}>
              {consent.decision
                ? DECISION_LABELS[consent.decision] ?? consent.decision
                : "Chưa quyết định"}
            </p>
            {consent.decision === "granted" && (
              <button
                type="button"
                disabled={busy === consent.consentType}
                onClick={() => onWithdraw(consent.consentType)}
                data-testid={`withdraw-${consent.consentType}`}
              >
                Rút đồng ý
              </button>
            )}
          </li>
        ))}
      </ul>
      <p>
        Rút đồng ý có hiệu lực ngay ở lượt tiếp theo. Dữ liệu đã lưu vẫn còn và
        bạn vẫn xem được.
      </p>

      <h3>Mang dữ liệu của bạn đi</h3>
      <p>
        Bản sao đầy đủ những gì Coach đang giữ. Markdown để đọc, JSON để đưa
        sang chỗ khác.
      </p>
      <button
        type="button"
        disabled={busy === "export"}
        onClick={() => onExport("markdown")}
        data-testid="export-markdown"
      >
        Tải bản đọc được (Markdown)
      </button>
      <button
        type="button"
        disabled={busy === "export"}
        onClick={() => onExport("json")}
        data-testid="export-json"
      >
        Tải bản đầy đủ (JSON)
      </button>

      <h3>Thùng rác</h3>
      {trash.length === 0 ? (
        <p data-testid="trash-empty">
          Không có gì trong thùng rác. Những gì bạn xoá sẽ nằm ở đây một thời
          gian trước khi mất hẳn.
        </p>
      ) : (
        <ul data-testid="trash-list">
          {trash.map((item) => {
            const key = `${item.entity_type}:${item.entity_id}`;
            return (
              <li key={key} data-testid={`trash-${key}`}>
                <p>{ENTITY_LABELS[item.entity_type] ?? item.entity_type}</p>
                {/* The date is the promise: recoverable until then, gone after.
                    A Trash with no visible deadline is just a slower delete. */}
                <p data-testid={`trash-when-${key}`}>
                  Xoá {item.deleted_at.slice(0, 10)} · lấy lại được tới{" "}
                  {item.purge_after.slice(0, 10)}
                </p>
                <button
                  type="button"
                  disabled={busy === key}
                  onClick={() => onRestore(item.entity_type, item.entity_id)}
                  data-testid={`restore-${key}`}
                >
                  Lấy lại
                </button>
                <button
                  type="button"
                  disabled={busy === key}
                  onClick={() => onPurge(item.entity_type, item.entity_id)}
                  data-testid={`purge-${key}`}
                >
                  Xoá hẳn ngay
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
