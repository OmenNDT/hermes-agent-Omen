import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Insights } from "./index";

afterEach(cleanup);

const INSIGHT = {
  id: "i1",
  content: "Điều làm tôi kẹt là sợ chọn sai",
  topic: null,
  confirmed_at: "2026-08-29T10:00:00Z",
};

describe("insights", () => {
  it("says where insights come from when there are none", () => {
    render(<Insights insights={[]} loading={false} error={null} />);
    expect(screen.getByTestId("insights-empty").textContent).toContain(
      "bấm Lưu",
    );
  });

  it("shows the whole set, not just the latest", () => {
    render(
      <Insights
        insights={[INSIGHT, { ...INSIGHT, id: "i2", content: "Điều thứ hai" }]}
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByTestId("insight-i1")).toBeTruthy();
    expect(screen.getByTestId("insight-i2")).toBeTruthy();
  });

  it("dates a learning by the day it was kept", () => {
    render(<Insights insights={[INSIGHT]} loading={false} error={null} />);
    expect(screen.getByTestId("insight-date-i1").textContent).toContain(
      "2026-08-29",
    );
  });

  it("offers no control that edits a confirmed record", () => {
    render(<Insights insights={[INSIGHT]} loading={false} error={null} />);
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("distinguishes loading from empty", () => {
    render(<Insights insights={[]} loading={true} error={null} />);
    expect(screen.getByTestId("insights-loading")).toBeTruthy();
    expect(screen.queryByTestId("insights-empty")).toBeNull();
  });
});
