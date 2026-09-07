/**
 * The six steps, named once.
 *
 * The session screen and the Journey both name these, and two copies would
 * eventually disagree — the same seam this codebase keeps closing. Kept in the
 * framework's own words rather than translated, because that is what the
 * Coachee sees during a session and a history that renamed them would read as
 * a different product.
 */

import type { Stage } from "@/store/session";

export const STAGE_LABELS: Record<Stage, string> = {
  pre_coaching: "Pre-Coaching",
  goal: "Goal",
  reality: "Reality",
  options: "Options",
  will: "Will",
  review: "Review",
};
