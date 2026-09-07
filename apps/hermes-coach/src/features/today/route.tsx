/**
 * Home wired to the backend.
 *
 * Nothing but the read: Home has no action of its own, because everything it
 * shows is produced somewhere else — goals inside a coaching turn, check-ins by
 * the scheduler. A button here would be a second way to create a record without
 * the confirmation the product requires.
 */

import { useCoachToday } from "@/lib/use-coach-today";
import { Today } from "./index";

export function TodayRoute() {
  const { today, error, loading } = useCoachToday();

  return (
    <Today
      goals={today?.goals ?? []}
      checkIns={today?.pending_check_ins ?? []}
      insight={today?.recent_insight ?? null}
      disclosure={today?.disclosure.note ?? null}
      loading={loading}
      error={error}
    />
  );
}
