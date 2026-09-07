/**
 * One candidate, one card, one decision.
 *
 * Confirmation is two round trips by design: minting an intent binds the exact
 * action *and* the exact edited text, so the server can refuse a confirmation
 * whose payload changed after the Coachee saw it. The UI therefore cannot mint
 * ahead of time — the intent is requested at the moment the Coachee commits.
 *
 * There is no control that resolves more than one card. Not a missing feature:
 * a batch accept would make the Coachee responsible for records they never
 * read individually.
 */

import { useState } from "react";

export type RecordAction = "accept" | "edit" | "discard";

export interface CandidateCard {
  id: string;
  kind: string;
  value: string;
}

export interface RecordConfirmationProps {
  candidates: CandidateCard[];
  /** Mint, then consume. Resolves when the record is official, or throws. */
  onResolve: (
    candidateId: string,
    action: RecordAction,
    editedValue: string | null,
  ) => Promise<void>;
}

const KIND_LABELS: Record<string, string> = {
  goal: "Mục tiêu",
  insight: "Nhận thức",
  commitment: "Cam kết",
  memory: "Ghi nhớ",
};

export function RecordConfirmation({
  candidates,
  onResolve,
}: RecordConfirmationProps) {
  if (candidates.length === 0) {
    return <p data-testid="no-candidates">Chưa có mục nào cần xác nhận.</p>;
  }

  return (
    <section aria-labelledby="records-heading">
      <h3 id="records-heading">Xác nhận từng mục</h3>
      <p>
        Mỗi mục được quyết riêng. Bạn có thể sửa trước khi lưu, hoặc bỏ đi.
      </p>
      <ul>
        {candidates.map((candidate) => (
          <li key={candidate.id}>
            <CandidateRow candidate={candidate} onResolve={onResolve} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function CandidateRow({
  candidate,
  onResolve,
}: {
  candidate: CandidateCard;
  onResolve: RecordConfirmationProps["onResolve"];
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(candidate.value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const label = KIND_LABELS[candidate.kind] ?? candidate.kind;
  const inputId = `edit-${candidate.id}`;

  async function resolve(action: RecordAction) {
    setBusy(true);
    setError(null);
    try {
      await onResolve(candidate.id, action, action === "edit" ? draft : null);
    } catch (reason) {
      // A refused confirmation leaves the candidate offerable, so the card
      // stays and keeps the Coachee's edit rather than discarding their work.
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article aria-label={`${label}: ${candidate.value}`}>
      <p>
        <span data-testid={`kind-${candidate.id}`}>{label}</span>
      </p>

      {editing ? (
        <>
          <label htmlFor={inputId}>Nội dung</label>
          <input
            id={inputId}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </>
      ) : (
        <p data-testid={`value-${candidate.id}`}>{candidate.value}</p>
      )}

      {editing ? (
        <>
          <button type="button" disabled={busy} onClick={() => resolve("edit")}>
            Lưu bản sửa
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setDraft(candidate.value);
              setEditing(false);
            }}
          >
            Huỷ sửa
          </button>
        </>
      ) : (
        <>
          <button type="button" disabled={busy} onClick={() => resolve("accept")}>
            Lưu
          </button>
          <button type="button" disabled={busy} onClick={() => setEditing(true)}>
            Sửa
          </button>
          <button type="button" disabled={busy} onClick={() => resolve("discard")}>
            Bỏ
          </button>
        </>
      )}

      {error && (
        <p role="alert" data-testid={`error-${candidate.id}`}>
          {error}
        </p>
      )}
    </article>
  );
}
