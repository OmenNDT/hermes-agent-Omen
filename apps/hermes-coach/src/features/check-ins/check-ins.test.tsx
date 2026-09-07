import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CheckInsProps, PendingCheckIn } from "./index";
import { CheckIns } from "./index";

afterEach(cleanup);

const CHECK_IN: PendingCheckIn = {
  id: "ci-1",
  commitment_id: "cm-1",
  action_text: "Thứ Hai nhắn anh Tuấn chọn 20 file",
  goal_id: "goal-1",
  scheduled_at: "2026-01-15T00:00:00Z",
  due_at: null,
  due: false,
  days_until: 14,
};

function renderScreen(overrides: Partial<CheckInsProps> = {}) {
  const props: CheckInsProps = {
    checkIns: [CHECK_IN],
    loading: false,
    error: null,
    busy: null,
    onAnswer: vi.fn(),
    ...overrides,
  };
  render(<CheckIns {...props} />);
  return props;
}

describe("with nothing outstanding", () => {
  it("says where check-ins come from rather than just being blank", () => {
    renderScreen({ checkIns: [] });
    expect(screen.getByTestId("check-ins-empty").textContent).toContain(
      "xác nhận một cam kết",
    );
    expect(
      screen.getByRole("link", { name: "mở một phiên" }).getAttribute("href"),
    ).toBe("#/coach");
  });

  it("distinguishes empty from not yet known", () => {
    renderScreen({ checkIns: [], loading: true });
    expect(screen.getByTestId("check-ins-loading")).toBeTruthy();
    expect(screen.queryByTestId("check-ins-empty")).toBeNull();
  });

  it("reports a failure instead of showing an empty list", () => {
    renderScreen({ error: "unknown_check_in: không tìm thấy" });
    expect(screen.getByTestId("check-ins-error").textContent).toContain(
      "unknown_check_in",
    );
    expect(screen.queryByTestId("check-ins")).toBeNull();
  });
});

describe("a check-in waiting", () => {
  // The commitment's own words are the question. An id or a date alone is
  // nothing the Coachee can recognise as a promise they made.
  it("shows the commitment, not just when it was scheduled", () => {
    renderScreen();
    expect(screen.getByTestId("check-in-text-ci-1").textContent).toBe(
      "Thứ Hai nhắn anh Tuấn chọn 20 file",
    );
    expect(screen.getByTestId("check-in-when-ci-1").textContent).toContain(
      "2026-01-15",
    );
  });

  it("keeps the commitment as it stands", async () => {
    const props = renderScreen();
    await userEvent.click(screen.getByTestId("keep-ci-1"));
    expect(props.onAnswer).toHaveBeenCalledWith("ci-1", "keep", {});
  });

  it("cancels only when that button is pressed", async () => {
    const props = renderScreen();
    await userEvent.click(screen.getByTestId("cancel-ci-1"));
    expect(props.onAnswer).toHaveBeenCalledWith("ci-1", "cancel", {});
  });

  it("accepts no second answer while one is in flight", () => {
    renderScreen({ busy: "ci-1" });
    expect(screen.getByTestId("keep-ci-1").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTestId("cancel-ci-1").hasAttribute("disabled")).toBe(true);
  });
});

describe("changing the commitment", () => {
  it("opens with the existing words, so a small edit is a small edit", async () => {
    renderScreen();
    await userEvent.click(screen.getByTestId("edit-ci-1"));
    expect((screen.getByLabelText("Cam kết mới") as HTMLInputElement).value).toBe(
      "Thứ Hai nhắn anh Tuấn chọn 20 file",
    );
  });

  it("sends the trimmed replacement", async () => {
    const props = renderScreen();
    await userEvent.click(screen.getByTestId("edit-ci-1"));
    const field = screen.getByLabelText("Cam kết mới");
    await userEvent.clear(field);
    await userEvent.type(field, "  Nhắn anh Tuấn chọn 10 file  ");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(props.onAnswer).toHaveBeenCalledWith("ci-1", "edit", {
      editedCommitment: "Nhắn anh Tuấn chọn 10 file",
    });
  });

  it("refuses to send an empty commitment", async () => {
    const props = renderScreen();
    await userEvent.click(screen.getByTestId("edit-ci-1"));
    await userEvent.clear(screen.getByLabelText("Cam kết mới"));
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(props.onAnswer).not.toHaveBeenCalled();
  });

  it("lets the Coachee back out without answering", async () => {
    const props = renderScreen();
    await userEvent.click(screen.getByTestId("edit-ci-1"));
    await userEvent.click(screen.getByTestId("dismiss-ci-1"));
    expect(props.onAnswer).not.toHaveBeenCalled();
    expect(screen.getByTestId("keep-ci-1")).toBeTruthy();
  });
});

describe("moving it", () => {
  it("sends a day as the instant the server stores", async () => {
    const props = renderScreen();
    await userEvent.click(screen.getByTestId("reschedule-ci-1"));
    const field = screen.getByLabelText("Hẹn lại vào ngày");
    await userEvent.clear(field);
    await userEvent.type(field, "2026-02-01");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(props.onAnswer).toHaveBeenCalledWith("ci-1", "reschedule", {
      rescheduledFor: "2026-02-01T00:00:00Z",
    });
  });

  it("offers one form at a time, not both at once", async () => {
    renderScreen();
    await userEvent.click(screen.getByTestId("reschedule-ci-1"));
    expect(screen.queryByLabelText("Cam kết mới")).toBeNull();
    expect(screen.getByLabelText("Hẹn lại vào ngày")).toBeTruthy();
  });
});


describe("due and still coming, told apart", () => {
  const DUE = { ...CHECK_IN, id: "ci-due", due: true, days_until: -2 };

  // A screen that showed "2 cam kết đang chờ" over one overdue and one due in
  // a fortnight tells the Coachee nothing about which needs them.
  it("counts the two kinds separately", () => {
    renderScreen({ checkIns: [DUE, CHECK_IN] });
    const summary = screen.getByTestId("check-ins-summary").textContent;
    expect(summary).toContain("1 cam kết đã tới hẹn");
    expect(summary).toContain("1 đang tới");
  });

  it("says an overdue one is overdue", () => {
    renderScreen({ checkIns: [DUE] });
    expect(screen.getByTestId("check-in-when-ci-due").textContent).toContain(
      "Quá hẹn 2 ngày",
    );
  });

  it("does not present something still coming as needing them now", () => {
    renderScreen();
    const when = screen.getByTestId("check-in-when-ci-1").textContent ?? "";
    expect(when).toContain("Còn 14 ngày");
    expect(when).not.toContain("tới hẹn");
  });
});
