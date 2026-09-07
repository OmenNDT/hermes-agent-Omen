import { useEffect, useState } from "react";

import { describeFailure, useCoachApi } from "@/lib/use-coach-today";
import type { Insight } from "./index";
import { Insights } from "./index";

export function InsightsRoute() {
  const api = useCoachApi();
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (api === null) return;
    let cancelled = false;
    api
      .call("coach.insights")
      .then((answer) => {
        if (cancelled) return;
        setInsights((answer as { insights: Insight[] }).insights);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(describeFailure(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <Insights
      insights={insights ?? []}
      loading={api !== null && insights === null && error === null}
      error={error}
    />
  );
}
