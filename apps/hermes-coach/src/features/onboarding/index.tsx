/**
 * Onboarding: what coaching is, what the storage is, then consent.
 *
 * The Coachee reads the role and boundaries, then the unencrypted-storage
 * disclosure, and only then is asked to decide. Each consent is its own pair of
 * buttons — there is no single "I agree to everything" control, because the two
 * decisions have different consequences and one of them is refusable without
 * losing the product.
 */

import { useState } from "react";

import {
  RecordConfirmation,
  type CandidateCard,
  type RecordAction,
} from "./record-confirmation";
import {
  LOCAL_STORAGE_CONSENT,
  MODEL_EGRESS_CONSENT,
  type ConsentDecision,
  type OnboardingState,
  type OnboardingStep,
  INITIAL_ONBOARDING,
  canGenerate,
  isComplete,
} from "./steps";

export interface OnboardingProps {
  /** Records one decision. Returns the decision the server settled on. */
  onConsent: (
    consentType: string,
    uiAction: "confirm" | "decline",
    controlId: string,
  ) => Promise<ConsentDecision>;
  onFinish?: () => void;
  disclosureNote: string;
  /** Candidates awaiting confirmation. Supplied by the server, never invented. */
  candidates?: CandidateCard[];
  onResolveCandidate?: (
    candidateId: string,
    action: RecordAction,
    editedValue: string | null,
  ) => Promise<void>;
  /** Asked once every record has been decided. */
  onCreateFirstGoal?: () => void;
}

const AGREEMENT_POINTS = [
  "Coach là Người đồng hành ngang vị thế với bạn, không phải chuyên gia đứng trên.",
  "Coach tin bạn có tiềm năng và năng lực tự giải quyết vấn đề của mình.",
  "Coach hỏi, không khuyên. Đây không phải tư vấn và không phải trị liệu.",
  "Bạn quyết định mọi mục tiêu, lựa chọn và cam kết; Coach không quyết thay.",
  "Phiên đi theo sáu bước: Pre-Coaching → Goal → Reality → Options → Will → Review.",
];

export function Onboarding({
  onConsent,
  onFinish,
  disclosureNote,
  candidates = [],
  onResolveCandidate,
  onCreateFirstGoal,
}: OnboardingProps) {
  const [state, setState] = useState<OnboardingState>(INITIAL_ONBOARDING);
  const [step, setStep] = useState<OnboardingStep>("agreement");
  const [busy, setBusy] = useState(false);

  async function decide(
    consentType: string,
    uiAction: "confirm" | "decline",
    controlId: string,
  ) {
    setBusy(true);
    try {
      const decision = await onConsent(consentType, uiAction, controlId);
      setState((current) => ({
        ...current,
        ...(consentType === LOCAL_STORAGE_CONSENT
          ? { localStorageConsent: decision }
          : { modelEgressConsent: decision }),
      }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="onboarding-heading">
      <h2 id="onboarding-heading">Bắt đầu với Hermes Coach</h2>

      {step === "agreement" && (
        <div data-testid="step-agreement">
          <h3>Coaching là gì và không là gì</h3>
          <ul>
            {AGREEMENT_POINTS.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => {
              setState((current) => ({ ...current, agreementAccepted: true }));
              setStep("disclosure");
            }}
          >
            Tôi đã hiểu và đồng ý
          </button>
        </div>
      )}

      {step === "disclosure" && (
        <div data-testid="step-disclosure">
          <h3>Dữ liệu của bạn lưu ở đâu</h3>
          {/* Shown before consent, not alongside it: the Coachee needs this to
              decide, so it cannot be a footnote under the buttons. */}
          <p data-testid="disclosure-note">{disclosureNote}</p>
          <button
            type="button"
            onClick={() => {
              setState((current) => ({ ...current, disclosureSeen: true }));
              setStep("consent");
            }}
          >
            Tôi đã đọc
          </button>
        </div>
      )}

      {step === "consent" && (
        <div data-testid="step-consent">
          <h3>Bạn cho phép những gì</h3>

          <fieldset>
            <legend>Lưu dữ liệu trên máy này</legend>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                decide(LOCAL_STORAGE_CONSENT, "confirm", "btn-local-confirm")
              }
            >
              Xác nhận
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                decide(LOCAL_STORAGE_CONSENT, "decline", "btn-local-decline")
              }
            >
              Từ chối
            </button>
            <p data-testid="local-decision">{describe(state.localStorageConsent)}</p>
          </fieldset>

          <fieldset>
            <legend>Gửi nội dung tới mô hình để tạo câu hỏi</legend>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                decide(MODEL_EGRESS_CONSENT, "confirm", "btn-egress-confirm")
              }
            >
              Xác nhận
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                decide(MODEL_EGRESS_CONSENT, "decline", "btn-egress-decline")
              }
            >
              Từ chối
            </button>
            <p data-testid="egress-decision">{describe(state.modelEgressConsent)}</p>
          </fieldset>

          {state.modelEgressConsent === "declined" && (
            // Declining is a supported outcome, so say what still works.
            <p role="status" data-testid="egress-declined-note">
              Bạn vẫn dùng được mục tiêu, ghi chép và quyền riêng tư. Chỉ phần
              tạo câu hỏi mới cần gửi dữ liệu đi.
            </p>
          )}

          {isComplete(state) && (
            <button
              type="button"
              onClick={() => {
                setStep("profile");
                onFinish?.();
              }}
            >
              Tiếp tục
            </button>
          )}
        </div>
      )}

      {step === "profile" && (
        <div data-testid="step-profile">
          <h3>Hồ sơ của bạn</h3>
          <p>
            {canGenerate(state)
              ? "Coach sẽ hỏi từng câu một."
              : "Chưa gửi dữ liệu đi, nên phần hỏi đáp tạm chưa dùng được."}
          </p>
          <button type="button" onClick={() => setStep("records")}>
            Xem các mục cần xác nhận
          </button>
        </div>
      )}

      {step === "records" && (
        <div data-testid="step-records">
          {onResolveCandidate && (
            <RecordConfirmation
              candidates={candidates}
              onResolve={onResolveCandidate}
            />
          )}
          {candidates.length === 0 && (
            // Asked only once nothing is left undecided: offering it while
            // records are pending would invite skipping past them.
            <div data-testid="first-goal-prompt">
              <p>Bạn muốn tạo mục tiêu coaching đầu tiên chứ?</p>
              <button type="button" onClick={() => onCreateFirstGoal?.()}>
                Tạo mục tiêu đầu tiên
              </button>
            </div>
          )}
        </div>
      )}

    </section>
  );
}

function describe(decision: ConsentDecision): string {
  if (decision === "granted") return "Đã xác nhận";
  if (decision === "declined") return "Đã từ chối";
  if (decision === "withdrawn") return "Đã rút";
  return "Chưa quyết định";
}
