import { useCoachToday } from "@/lib/use-coach-today";
import { Goals } from "./index";

export function GoalsRoute() {
  const { today, error, loading } = useCoachToday();

  return (
    <Goals goals={today?.goals ?? []} loading={loading} error={error} />
  );
}
