import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { $connection, applyServerSnapshot, resetSession } from "@/store/session";
import { ROUTES, currentPath, routeFor } from "./routes";
import { Shell } from "./shell";

beforeEach(() => {
  window.location.hash = "";
  resetSession();
  $connection.set("online");
});

afterEach(cleanup);

describe("route table", () => {
  it("covers every destination the product promises", () => {
    expect(ROUTES.map((route) => route.path)).toEqual([
      "/",
      "/onboarding",
      "/coach",
      "/goals",
      "/journey",
      "/insights",
      "/check-ins",
      "/privacy",
    ]);
  });

  it("has no route for a terminal, tool palette or general chat", () => {
    // Coach is not a second Hermes dashboard.
    for (const route of ROUTES) {
      expect(route.path).not.toMatch(/pty|terminal|tools|chat|dashboard/);
    }
  });

  // The last placeholder went with /journey. A destination in the navigation
  // that opens a "coming soon" panel is a promise the product is not keeping,
  // and this stops one creeping back in unnoticed.
  it("has no placeholder destinations left", () => {
    for (const route of ROUTES) {
      expect(route.component.name).not.toMatch(/placeholder/i);
    }
  });

  it("has no voice route", () => {
    for (const route of ROUTES) {
      expect(`${route.path} ${route.label}`.toLowerCase()).not.toMatch(
        /voice|audio|micro|stt|tts|giọng/,
      );
    }
  });

  it("falls back to home for an unknown path", () => {
    expect(routeFor("/nope").path).toBe("/");
  });

  it("reads the path out of the hash", () => {
    expect(currentPath("#/goals")).toBe("/goals");
    expect(currentPath("")).toBe("/");
    expect(currentPath("#garbage")).toBe("/");
  });
});

describe("shell", () => {
  it("renders navigation and main as landmarks", () => {
    render(<Shell />);
    expect(screen.getByRole("navigation")).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
  });

  it("offers a skip link before the navigation", () => {
    render(<Shell />);
    const skip = screen.getByText("Bỏ qua điều hướng");
    expect(skip.getAttribute("href")).toBe("#coach-main");
  });

  it("marks the active destination for assistive technology", () => {
    render(<Shell />);
    const active = screen.getByRole("link", { name: "Hôm nay" });
    expect(active.getAttribute("aria-current")).toBe("page");
  });

  it("does not mark inactive destinations", () => {
    render(<Shell />);
    const other = screen.getByRole("link", { name: "Mục tiêu" });
    expect(other.getAttribute("aria-current")).toBeNull();
  });

  it("gives main a focus target so keyboard users land somewhere", () => {
    render(<Shell />);
    expect(screen.getByRole("main").getAttribute("tabindex")).toBe("-1");
  });

  it("shows the route heading", () => {
    window.location.hash = "#/privacy";
    render(<Shell />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Quyền riêng tư",
    );
  });
});

describe("degraded mode", () => {
  it("says so in words when the backend is unreachable", () => {
    $connection.set("offline");
    render(<Shell />);
    const notice = screen.getByTestId("degraded-notice");
    expect(notice.textContent).toMatch(/Dữ liệu đã lưu vẫn xem được/);
  });

  it("announces the notice as a status rather than silently disabling", () => {
    $connection.set("offline");
    render(<Shell />);
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("keeps navigation usable while offline", () => {
    // Local dashboard and privacy functions must survive losing the model.
    $connection.set("offline");
    render(<Shell />);
    expect(screen.getAllByRole("link").length).toBeGreaterThan(ROUTES.length - 1);
  });

  it("shows no notice when generation is available", () => {
    render(<Shell />);
    expect(screen.queryByTestId("degraded-notice")).toBeNull();
  });

  it("pauses coaching without disconnecting when urgent", () => {
    applyServerSnapshot({ safetyState: "urgent" });
    render(<Shell />);
    expect(screen.getByTestId("degraded-notice").textContent).toMatch(
      /Phiên coaching tạm dừng/,
    );
  });
});
