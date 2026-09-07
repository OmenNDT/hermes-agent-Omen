/**
 * Privacy wired to the backend.
 *
 * The decisions are read one scope at a time because that is how the server
 * stores them — a normalized type and scope pair — and asking for a summary the
 * server does not keep would mean inventing one here.
 */

import { useCallback, useEffect, useState } from "react";

import {
  describeFailure,
  useCoachApi,
  useCoachToday,
} from "@/lib/use-coach-today";
import type { ConsentLine, Decision, TrashItem } from "./index";
import { Privacy } from "./index";

const SCOPES: { consentType: string; label: string; meaning: string }[] = [
  {
    consentType: "local_storage",
    label: "Lưu dữ liệu trên máy này",
    meaning: "Mục tiêu, nhận thức và bản ghi phiên được giữ trong máy bạn.",
  },
  {
    consentType: "model_egress",
    label: "Gửi nội dung phiên tới mô hình",
    meaning: "Không có mục này thì phần hỏi đáp dừng; dữ liệu đã lưu vẫn xem được.",
  },
];

export function PrivacyRoute() {
  const api = useCoachApi();
  const { today, error: todayError, loading } = useCoachToday();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  // Counted, not guessed: `coach.today` carries only the latest insight, and a
  // privacy screen that reported "1" when there are nine would be worse than
  // reporting nothing.
  const [insightCount, setInsightCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [trash, setTrash] = useState<TrashItem[]>([]);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (api === null) return;
    let cancelled = false;
    Promise.all(
      SCOPES.map((scope) =>
        api
          .call("coach.consent.state", {
            consent_type: scope.consentType,
            scope: {},
          })
          .then((answer) => [
            scope.consentType,
            (answer as { decision: Decision }).decision,
          ]),
      ),
    )
      .then((pairs) => {
        if (cancelled) return;
        setDecisions(Object.fromEntries(pairs) as Record<string, Decision>);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(describeFailure(reason));
      });
    api
      .call("coach.trash")
      .then((answer) => {
        if (cancelled) return;
        setTrash((answer as { items: TrashItem[] }).items);
      })
      .catch(() => {
        // Same reasoning as the count below: a failed Trash read must not blank
        // the consent decisions, which are the part of this screen that matters.
        if (!cancelled) setTrash([]);
      });
    api
      .call("coach.insights")
      .then((answer) => {
        if (cancelled) return;
        setInsightCount((answer as { insights: unknown[] }).insights.length);
      })
      .catch(() => {
        // A failed count must not blank the consent decisions, which are the
        // part of this screen that matters.
        if (!cancelled) setInsightCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [api, attempt]);

  const withdraw = useCallback(
    (consentType: string) => {
      if (api === null) return;
      setBusy(consentType);
      api
        .call("coach.consent.record", {
          event_id: crypto.randomUUID(),
          consent_type: consentType,
          scope: {},
          ui_action: "withdraw",
          // The server refuses consent evidence with no trusted control behind
          // it, and this is the control.
          control_id: `btn-withdraw-${consentType}`,
        })
        .then(() => setAttempt((count) => count + 1))
        .catch((reason: unknown) => setError(describeFailure(reason)))
        .finally(() => setBusy(null));
    },
    [api],
  );

  const exportData = useCallback(
    (format: "json" | "markdown") => {
      if (api === null) return;
      setBusy("export");
      api
        .call("coach.export", { format })
        .then((answer) => {
          // Handed to the browser as a file rather than rendered on the page:
          // an export the Coachee cannot keep is not an export.
          const payload = answer as { markdown?: string; data?: unknown };
          const text =
            format === "markdown"
              ? (payload.markdown ?? "")
              : JSON.stringify(payload.data, null, 2);
          const blob = new Blob([text], {
            type: format === "markdown" ? "text/markdown" : "application/json",
          });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `hermes-coach.${format === "markdown" ? "md" : "json"}`;
          link.click();
          URL.revokeObjectURL(url);
        })
        .catch((reason: unknown) => setError(describeFailure(reason)))
        .finally(() => setBusy(null));
    },
    [api],
  );

  const act = useCallback(
    (method: string, entityType: string, entityId: string, extra: object = {}) => {
      if (api === null) return;
      setBusy(`${entityType}:${entityId}`);
      api
        .call(method, { entity_type: entityType, entity_id: entityId, ...extra })
        .then(() => setAttempt((count) => count + 1))
        .catch((reason: unknown) => setError(describeFailure(reason)))
        .finally(() => setBusy(null));
    },
    [api],
  );

  const restore = useCallback(
    (entityType: string, entityId: string) =>
      act("coach.trash.restore", entityType, entityId),
    [act],
  );

  const purge = useCallback(
    (entityType: string, entityId: string) =>
      // Irreversible, and the server refuses it without a trusted control id.
      act("coach.trash.purge", entityType, entityId, {
        control_id: "btn-purge-confirm",
      }),
    [act],
  );

  const consents: ConsentLine[] = SCOPES.map((scope) => ({
    ...scope,
    decision: decisions[scope.consentType] ?? null,
  }));

  return (
    <Privacy
      disclosure={today?.disclosure.note ?? null}
      encryptedAtRest={today?.disclosure.encrypted_at_rest ?? null}
      consents={consents}
      storedCounts={
        today && insightCount !== null
          ? { goals: today.goals.length, insights: insightCount }
          : null
      }
      loading={loading}
      error={error ?? todayError}
      trash={trash}
      busy={busy}
      onWithdraw={withdraw}
      onExport={exportData}
      onRestore={restore}
      onPurge={purge}
    />
  );
}
