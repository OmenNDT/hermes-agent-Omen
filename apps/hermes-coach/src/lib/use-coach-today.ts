/**
 * The one read every non-session screen needs.
 *
 * Home, Goals and Privacy all answer from `coach.today`, so they share this
 * rather than each opening their own call and drifting into three slightly
 * different ideas of what the profile currently holds.
 *
 * The state is set inside the promise callback, never synchronously in the
 * effect body — that is what `react-hooks/set-state-in-effect` forbids, and it
 * is also the honest shape: the answer arrives later.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useStore } from "@nanostores/react";

import type { CoachApi } from "@/lib/coach-api";
import { CoachRpcError } from "@/lib/coach-api";
import { coachApi } from "@/lib/connection";
import { $connection } from "@/store/session";

export interface TodayGoal {
  id: string;
  title: string;
  status: string;
  target_date: string | null;
}

export interface TodayCheckIn {
  id: string;
  commitment_id: string;
  /** The commitment's own words. A bare id is nothing a Coachee can act on. */
  action_text: string;
  goal_id: string;
  scheduled_at: string;
  due_at: string | null;
  /** Has the day arrived. An item still coming must not read as needing them now. */
  due: boolean;
  /** Whole days by calendar date; negative when overdue. */
  days_until: number | null;
}

export interface TodayInsight {
  id: string;
  content: string;
}

export interface TodayPayload {
  profile_id: string;
  goals: TodayGoal[];
  pending_check_ins: TodayCheckIn[];
  recent_insight: TodayInsight | null;
  disclosure: { encrypted_at_rest: boolean; note: string; version: string };
}

export interface TodayState {
  today: TodayPayload | null;
  error: string | null;
  /** True until the first answer or failure. Distinguishes empty from unknown. */
  loading: boolean;
  reload: () => void;
}

/**
 * The connected client, or null.
 *
 * Derived during render from the connection state rather than stored by an
 * effect: the shell renders before `main.tsx` finishes connecting, so a screen
 * that grabbed the client once at mount would stay broken for the life of the
 * page.
 */
export function useCoachApi(): CoachApi | null {
  const connection = useStore($connection);
  return useMemo<CoachApi | null>(() => {
    if (connection !== "online") return null;
    try {
      return coachApi();
    } catch {
      return null;
    }
  }, [connection]);
}

export function describeFailure(reason: unknown): string {
  return reason instanceof CoachRpcError
    ? `${reason.code}: ${reason.message}`
    : (reason as Error).message;
}

export function useCoachToday(): TodayState {
  const [today, setToday] = useState<TodayPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const api = useCoachApi();

  useEffect(() => {
    if (api === null) return;
    let cancelled = false;
    api
      .call("coach.today")
      .then((answer) => {
        if (cancelled) return;
        setToday(answer as TodayPayload);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(describeFailure(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [api, attempt]);

  const reload = useCallback(() => setAttempt((count) => count + 1), []);

  return {
    today,
    error,
    // Offline is not loading: it is a settled answer of "cannot know".
    loading: api !== null && today === null && error === null,
    reload,
  };
}
