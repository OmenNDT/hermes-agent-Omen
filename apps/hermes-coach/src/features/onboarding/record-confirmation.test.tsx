import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  RecordConfirmation,
  type CandidateCard,
  type RecordConfirmationProps,
} from "./record-confirmation";

afterEach(cleanup);

const GOAL: CandidateCard = {
  id: "cand-1",
  kind: "goal",
  value: "Chuyển sang vai trò kiến trúc sư",
};

const INSIGHT: CandidateCard = {
  id: "cand-2",
  kind: "insight",
  value: "Tôi né tránh xung đột",
};

type Resolver = RecordConfirmationProps["onResolve"];

function setup(
  candidates: CandidateCard[] = [GOAL],
  onResolve: Resolver = vi.fn<Resolver>(async () => {}),
) {
  const user = userEvent.setup();
  render(<RecordConfirmation candidates={candidates} onResolve={onResolve} />);
  return { user, onResolve };
}

describe("one decision per record", () => {
  it("renders a card per candidate", () => {
    setup([GOAL, INSIGHT]);
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("offers save, edit and discard on each card", () => {
    setup([GOAL, INSIGHT]);
    expect(screen.getAllByRole("button", { name: "Lưu" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Sửa" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Bỏ" })).toHaveLength(2);
  });

  it("has no control that resolves more than one card", () => {
    // A batch accept makes the Coachee responsible for records they never read.
    setup([GOAL, INSIGHT]);
    for (const button of screen.getAllByRole("button")) {
      expect(button.textContent?.toLowerCase()).not.toMatch(
        /tất cả|lưu hết|accept all|confirm all/,
      );
    }
  });

  it("resolves exactly the card that was acted on", async () => {
    const { user, onResolve } = setup([GOAL, INSIGHT]);
    await user.click(screen.getAllByRole("button", { name: "Lưu" })[1]);
    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledWith("cand-2", "accept", null);
  });

  it("says so when there is nothing to confirm", () => {
    setup([]);
    expect(screen.getByTestId("no-candidates")).toBeTruthy();
  });
});

describe("accept", () => {
  it("sends no edited value", async () => {
    const { user, onResolve } = setup();
    await user.click(screen.getByRole("button", { name: "Lưu" }));
    expect(onResolve).toHaveBeenCalledWith("cand-1", "accept", null);
  });
});

describe("discard", () => {
  it("sends discard for that card alone", async () => {
    const { user, onResolve } = setup([GOAL, INSIGHT]);
    await user.click(screen.getAllByRole("button", { name: "Bỏ" })[0]);
    expect(onResolve).toHaveBeenCalledWith("cand-1", "discard", null);
  });
});

describe("edit", () => {
  it("shows the current text in a labelled field", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Sửa" }));
    const field = screen.getByLabelText("Nội dung") as HTMLInputElement;
    expect(field.value).toBe(GOAL.value);
  });

  it("sends the edited text, not the original", async () => {
    const { user, onResolve } = setup();
    await user.click(screen.getByRole("button", { name: "Sửa" }));
    const field = screen.getByLabelText("Nội dung");
    await user.clear(field);
    await user.type(field, "Chuyển vai trò trong 6 tháng");
    await user.click(screen.getByRole("button", { name: "Lưu bản sửa" }));
    expect(onResolve).toHaveBeenCalledWith(
      "cand-1",
      "edit",
      "Chuyển vai trò trong 6 tháng",
    );
  });

  it("hides accept and discard while editing", async () => {
    // One action at a time: an accept next to an unsaved edit is ambiguous.
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Sửa" }));
    expect(screen.queryByRole("button", { name: "Lưu" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Bỏ" })).toBeNull();
  });

  it("restores the original text when the edit is abandoned", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Sửa" }));
    await user.clear(screen.getByLabelText("Nội dung"));
    await user.type(screen.getByLabelText("Nội dung"), "nháp");
    await user.click(screen.getByRole("button", { name: "Huỷ sửa" }));
    expect(screen.getByTestId("value-cand-1").textContent).toBe(GOAL.value);
  });

  it("does not resolve anything when an edit is abandoned", async () => {
    const { user, onResolve } = setup();
    await user.click(screen.getByRole("button", { name: "Sửa" }));
    await user.click(screen.getByRole("button", { name: "Huỷ sửa" }));
    expect(onResolve).not.toHaveBeenCalled();
  });
});

describe("a refused confirmation", () => {
  it("reports the reason on the card it belongs to", async () => {
    const onResolve = vi.fn<Resolver>(async () => {
      throw new Error("intent was already consumed");
    });
    const { user } = setup([GOAL, INSIGHT], onResolve);
    await user.click(screen.getAllByRole("button", { name: "Lưu" })[0]);
    expect(screen.getByTestId("error-cand-1").textContent).toMatch(
      /already consumed/,
    );
    expect(screen.queryByTestId("error-cand-2")).toBeNull();
  });

  it("keeps the card offerable rather than burning it", async () => {
    const onResolve = vi
      .fn<Resolver>()
      .mockRejectedValueOnce(new Error("refused"))
      .mockResolvedValueOnce(undefined);
    const { user } = setup([GOAL], onResolve);
    await user.click(screen.getByRole("button", { name: "Lưu" }));
    await user.click(screen.getByRole("button", { name: "Lưu" }));
    expect(onResolve).toHaveBeenCalledTimes(2);
  });

  it("keeps the Coachee's edit after a refusal", async () => {
    const onResolve = vi.fn<Resolver>(async () => {
      throw new Error("refused");
    });
    const { user } = setup([GOAL], onResolve);
    await user.click(screen.getByRole("button", { name: "Sửa" }));
    await user.clear(screen.getByLabelText("Nội dung"));
    await user.type(screen.getByLabelText("Nội dung"), "bản sửa của tôi");
    await user.click(screen.getByRole("button", { name: "Lưu bản sửa" }));
    expect((screen.getByLabelText("Nội dung") as HTMLInputElement).value).toBe(
      "bản sửa của tôi",
    );
  });
});

describe("accessibility", () => {
  it("labels each card by kind and content", () => {
    setup([GOAL]);
    expect(
      screen.getByRole("article", { name: /Mục tiêu: Chuyển sang vai trò/ }),
    ).toBeTruthy();
  });

  it("names the record kind in words, not only by colour or icon", () => {
    setup([GOAL, INSIGHT]);
    expect(screen.getByTestId("kind-cand-1").textContent).toBe("Mục tiêu");
    expect(screen.getByTestId("kind-cand-2").textContent).toBe("Nhận thức");
  });

  it("announces a refusal as an alert", async () => {
    const onResolve = vi.fn<Resolver>(async () => {
      throw new Error("refused");
    });
    const { user } = setup([GOAL], onResolve);
    await user.click(screen.getByRole("button", { name: "Lưu" }));
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("reaches every control on a card by keyboard", async () => {
    const { user } = setup([GOAL]);
    const reached: string[] = [];
    for (let i = 0; i < 3; i += 1) {
      await user.tab();
      reached.push(document.activeElement?.textContent ?? "");
    }
    expect(reached).toEqual(["Lưu", "Sửa", "Bỏ"]);
  });

  it("falls back to the raw kind for an unknown record type", () => {
    setup([{ id: "cand-9", kind: "mystery", value: "x" }]);
    expect(screen.getByTestId("kind-cand-9").textContent).toBe("mystery");
  });
});
