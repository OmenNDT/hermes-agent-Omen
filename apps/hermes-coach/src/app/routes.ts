/**
 * The Coach route table.
 *
 * Hash routing, hand-rolled. This is a single-user local app with eight
 * destinations and no SEO or deep-link requirement, so a router dependency
 * would be more surface than the problem needs.
 *
 * The table is data, not JSX, so a test can assert what exists — and what does
 * not — without rendering anything.
 *
 * Every destination is now a real screen. The `placeholder` helper this file
 * used to import is gone with the last of them.
 */

import type { ComponentType } from "react";

import { CheckInsRoute } from "@/features/check-ins/route";
import { CoachSessionRoute } from "@/features/coach/route";
import { GoalsRoute } from "@/features/goals/route";
import { InsightsRoute } from "@/features/insights/route";
import { JourneyRoute } from "@/features/journey/route";
import { OnboardingRoute } from "@/features/onboarding/route";
import { PrivacyRoute } from "@/features/privacy/route";
import { TodayRoute } from "@/features/today/route";

export interface CoachRoute {
  path: string;
  /** Shown in navigation and as the document heading. */
  label: string;
  component: ComponentType;
}

export const ROUTES: CoachRoute[] = [
  { path: "/", label: "Hôm nay", component: TodayRoute },
  { path: "/onboarding", label: "Bắt đầu", component: OnboardingRoute },
  { path: "/coach", label: "Phiên coaching", component: CoachSessionRoute },
  { path: "/goals", label: "Mục tiêu", component: GoalsRoute },
  { path: "/journey", label: "Hành trình", component: JourneyRoute },
  { path: "/insights", label: "Nhận thức", component: InsightsRoute },
  { path: "/check-ins", label: "Check-in", component: CheckInsRoute },
  { path: "/privacy", label: "Quyền riêng tư", component: PrivacyRoute },
];

export const HOME_PATH = "/";

export function routeFor(path: string): CoachRoute {
  return ROUTES.find((route) => route.path === path) ?? ROUTES[0];
}

/** Read the current path from the hash, defaulting to home. */
export function currentPath(hash: string): string {
  const raw = hash.replace(/^#/, "");
  return raw.startsWith("/") ? raw : HOME_PATH;
}
