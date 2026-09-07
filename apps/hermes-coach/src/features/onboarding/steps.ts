/**
 * Onboarding as an ordered gate, not a wizard you can skip through.
 *
 * The order is load-bearing. The Coachee is told what coaching is and is not
 * before agreeing to it; the unencrypted-storage disclosure is shown before any
 * consent is collected; and consent is a separate step from the agreement so a
 * single click cannot stand for both.
 *
 * This module is pure data and predicates so the rules can be tested without
 * rendering anything.
 */

export const ONBOARDING_STEPS = [
  "agreement",
  "disclosure",
  "consent",
  "profile",
  "records",
] as const;

export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];

/** Consent kinds collected during onboarding, each independent. */
export const LOCAL_STORAGE_CONSENT = "local_storage";
export const MODEL_EGRESS_CONSENT = "model_egress";

export interface OnboardingState {
  /** Set only after the Coachee accepts the role and boundary explanation. */
  agreementAccepted: boolean;
  /** Set only after the disclosure has actually been shown. */
  disclosureSeen: boolean;
  localStorageConsent: ConsentDecision;
  modelEgressConsent: ConsentDecision;
}

export type ConsentDecision = "granted" | "declined" | "withdrawn" | null;

export const INITIAL_ONBOARDING: OnboardingState = {
  agreementAccepted: false,
  disclosureSeen: false,
  localStorageConsent: null,
  modelEgressConsent: null,
};

/**
 * Whether a step may be entered yet.
 *
 * Declining consent does not block progress: the product must remain usable
 * locally, with generation unavailable. Only the agreement and the disclosure
 * are hard gates, because they are what the Coachee needs in order to decide.
 */
export function canEnter(step: OnboardingStep, state: OnboardingState): boolean {
  switch (step) {
    case "agreement":
      return true;
    case "disclosure":
      return state.agreementAccepted;
    case "consent":
      return state.agreementAccepted && state.disclosureSeen;
    case "profile":
    case "records":
      return (
        state.agreementAccepted &&
        state.disclosureSeen &&
        state.localStorageConsent !== null
      );
  }
}

export function nextStep(
  current: OnboardingStep,
  state: OnboardingState,
): OnboardingStep | null {
  const index = ONBOARDING_STEPS.indexOf(current);
  const candidate = ONBOARDING_STEPS[index + 1];
  if (!candidate) return null;
  return canEnter(candidate, state) ? candidate : null;
}

/** Onboarding is finished when the Coachee has decided, either way. */
export function isComplete(state: OnboardingState): boolean {
  return (
    state.agreementAccepted &&
    state.disclosureSeen &&
    state.localStorageConsent !== null &&
    state.modelEgressConsent !== null
  );
}

/**
 * Whether a coaching turn can run.
 *
 * Local storage alone is not enough: sending anything to a model needs its own
 * granted scope, and a decline there leaves the rest of the product working.
 */
export function canGenerate(state: OnboardingState): boolean {
  return state.modelEgressConsent === "granted";
}
