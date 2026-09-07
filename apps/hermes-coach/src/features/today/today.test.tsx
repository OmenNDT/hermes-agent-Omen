import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { TodayProps } from "./index";
import { Today } from "./index";

afterEach(cleanup);

function renderToday(overrides: Partial<TodayProps> = {}) {
  const props: TodayProps = {
    goals: [],
    checkIns: [],
    insight: null,
    disclosure: "Dữ liệu Coach lưu trên máy này và không được mã hoá.",
    loading: false,
    error: null,
    ...overrides,
  };
  render(<Today {...props} />);
  return props;
}

const GOAL = {
  id: "g1",
  title: "Đến 28/02/2027 có một sản phẩm chạy được",
  status: "active",
  target_date: null,
};

const CHECK_IN = {
  id: "ci-1",
  commitment_id: "cm-1",
  action_text: "Thứ Hai nhắn anh Tuấn chọn 20 file",
  goal_id: "g1",
  scheduled_at: "2026-01-15T00:00:00Z",
  due_at: null,
  due: false,
  days_until: 14,
};

describe("what needs the Coachee today", () => {
  // Home used to render the bare `scheduled_at` string. "2026-01-15T00:00:00Z"
  // is not something anyone recognises as a promise they made, and it was the
  // only thing this panel had ever shown — because until check-ins were wired,
  // the list was always empty and nobody saw it.
  it("names the commitment, not just when it is due", () => {
    renderToday({ checkIns: [CHECK_IN] });
    const item = screen.getByTestId("today-check-in-ci-1");
    expect(item.textContent).toContain("Thứ Hai nhắn anh Tuấn chọn 20 file");
    expect(screen.queryByTestId("today-no-check-ins")).toBeNull();
  });

  it("shows the day without the machine timestamp around it", () => {
    renderToday({ checkIns: [CHECK_IN] });
    const item = screen.getByTestId("today-check-in-ci-1");
    expect(item.textContent).toContain("2026-01-15");
    expect(item.textContent).not.toContain("T00:00:00Z");
  });

  // The heading used to say "Cần bạn hôm nay" over a commitment due in a
  // fortnight. Keeping the row and fixing the heading is the whole trade:
  // Home stays useful in the thirteen quiet days without lying about them.
  it("does not claim a commitment still coming needs them today", () => {
    renderToday({ checkIns: [CHECK_IN] });
    expect(screen.queryByText("Cần bạn hôm nay")).toBeNull();
    expect(
      screen.getByTestId("today-check-in-when-ci-1").textContent,
    ).toContain("Còn 14 ngày");
  });

  it("marks one that has come due as due", () => {
    renderToday({
      checkIns: [{ ...CHECK_IN, due: true, days_until: 0 }],
    });
    expect(
      screen.getByTestId("today-check-in-when-ci-1").textContent,
    ).toContain("Đã tới hẹn");
  });
});

describe("first run", () => {
  it("says what to do next instead of showing a blank panel", () => {
    renderToday();
    expect(screen.getByTestId("today-no-goals").textContent).toContain(
      "mở một phiên",
    );
    expect(screen.getByTestId("today-no-check-ins")).toBeTruthy();
    expect(screen.getByTestId("today-no-insight")).toBeTruthy();
  });

  it("points the empty state at the only place goals come from", () => {
    renderToday();
    const link = screen.getByRole("link", { name: "mở một phiên" });
    expect(link.getAttribute("href")).toBe("#/coach");
  });
});

describe("with a profile behind it", () => {
  it("shows the destination in the Coachee's own words", () => {
    renderToday({ goals: [GOAL] });
    expect(screen.getByTestId("today-goal-g1").textContent).toContain(
      "Đến 28/02/2027 có một sản phẩm chạy được",
    );
  });

  it("shows a target date only when there is one", () => {
    renderToday({ goals: [GOAL] });
    expect(screen.queryByTestId("today-goal-date-g1")).toBeNull();
    cleanup();
    renderToday({ goals: [{ ...GOAL, target_date: "2027-02-28" }] });
    expect(screen.getByTestId("today-goal-date-g1").textContent).toContain(
      "2027-02-28",
    );
  });

  it("shows one learning, not a scroll of them", () => {
    renderToday({ insight: { id: "i1", content: "Tôi sợ chọn sai" } });
    expect(screen.getByTestId("today-insight").textContent).toBe(
      "Tôi sợ chọn sai",
    );
  });

  it("keeps the unencrypted-storage disclosure on the home screen", () => {
    renderToday();
    expect(screen.getByTestId("today-disclosure").textContent).toContain(
      "không được mã hoá",
    );
  });
});

describe("when the answer has not arrived", () => {
  it("says loading rather than claiming the profile is empty", () => {
    renderToday({ loading: true });
    expect(screen.getByTestId("today-loading")).toBeTruthy();
    expect(screen.queryByTestId("today-no-goals")).toBeNull();
  });

  it("reports a failure as an alert", () => {
    renderToday({ error: "internal_error: không đọc được" });
    expect(screen.getByRole("alert").textContent).toContain("internal_error");
  });
});
