import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Goals } from "./index";

afterEach(cleanup);

const GOAL = {
  id: "g1",
  title: "Đến 28/02/2027 có một sản phẩm chạy được",
  status: "active",
  target_date: "2027-02-28",
};

describe("goals", () => {
  it("explains where goals come from when there are none", () => {
    render(<Goals goals={[]} loading={false} error={null} />);
    expect(screen.getByTestId("goals-empty").textContent).toContain("bấm Lưu");
  });

  it("lists confirmed goals with a readable status", () => {
    render(<Goals goals={[GOAL]} loading={false} error={null} />);
    expect(screen.getByTestId("goal-g1").textContent).toContain(
      "Đến 28/02/2027 có một sản phẩm chạy được",
    );
    expect(screen.getByTestId("goal-status-g1").textContent).toContain(
      "Đang theo",
    );
  });

  it("falls back to the raw status rather than hiding one it does not know", () => {
    render(
      <Goals
        goals={[{ ...GOAL, status: "something_new" }]}
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByTestId("goal-status-g1").textContent).toContain(
      "something_new",
    );
  });

  it("offers no control that edits a confirmed record", () => {
    // Editing happens on the candidate card, with the confirmation evidence
    // attached. A quiet edit here would bypass that entirely.
    render(<Goals goals={[GOAL]} loading={false} error={null} />);
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("distinguishes loading from empty", () => {
    render(<Goals goals={[]} loading={true} error={null} />);
    expect(screen.getByTestId("goals-loading")).toBeTruthy();
    expect(screen.queryByTestId("goals-empty")).toBeNull();
  });
});
