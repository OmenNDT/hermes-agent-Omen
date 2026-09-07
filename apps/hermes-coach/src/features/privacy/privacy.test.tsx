import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PrivacyProps } from "./index";
import { Privacy } from "./index";

afterEach(cleanup);

function renderPrivacy(overrides: Partial<PrivacyProps> = {}) {
  const props: PrivacyProps = {
    disclosure: "Dữ liệu Coach lưu trên máy này và không được mã hoá.",
    encryptedAtRest: false,
    consents: [
      {
        consentType: "model_egress",
        label: "Gửi nội dung phiên tới mô hình",
        meaning: "Không có mục này thì phần hỏi đáp dừng.",
        decision: "granted",
      },
      {
        consentType: "local_storage",
        label: "Lưu dữ liệu trên máy này",
        meaning: "Bản ghi được giữ trong máy bạn.",
        decision: "declined",
      },
    ],
    storedCounts: { goals: 2, insights: 5 },
    trash: [],
    loading: false,
    error: null,
    busy: null,
    onWithdraw: vi.fn(),
    onExport: vi.fn(),
    onRestore: vi.fn(),
    onPurge: vi.fn(),
    ...overrides,
  };
  render(<Privacy {...props} />);
  return props;
}

describe("what is being held", () => {
  it("shows the disclosure in the backend's own words", () => {
    renderPrivacy();
    expect(screen.getByTestId("privacy-disclosure").textContent).toContain(
      "không được mã hoá",
    );
  });

  it("states plainly that storage is not encrypted", () => {
    renderPrivacy();
    expect(screen.getByTestId("privacy-not-encrypted")).toBeTruthy();
  });

  it("counts what is stored rather than implying it", () => {
    renderPrivacy();
    const counts = screen.getByTestId("privacy-counts").textContent ?? "";
    expect(counts).toContain("2");
    expect(counts).toContain("5");
  });

  it("says nothing about counts it could not read", () => {
    renderPrivacy({ storedCounts: null });
    expect(screen.queryByTestId("privacy-counts")).toBeNull();
  });
});

describe("standing decisions", () => {
  it("shows each scope separately, with what it means", () => {
    renderPrivacy();
    expect(
      screen.getByTestId("consent-decision-model_egress").textContent,
    ).toContain("Đã đồng ý");
    expect(
      screen.getByTestId("consent-meaning-local_storage").textContent,
    ).toContain("máy bạn");
  });

  it("offers withdrawal only for a scope that is currently granted", () => {
    renderPrivacy();
    expect(screen.getByTestId("withdraw-model_egress")).toBeTruthy();
    expect(screen.queryByTestId("withdraw-local_storage")).toBeNull();
  });

  it("withdraws one scope without touching the other", async () => {
    // A single master switch would force a Coachee who only wanted to stop
    // sending data to also give up their own records.
    const props = renderPrivacy();
    await userEvent.click(screen.getByTestId("withdraw-model_egress"));
    expect(props.onWithdraw).toHaveBeenCalledTimes(1);
    expect(props.onWithdraw).toHaveBeenCalledWith("model_egress");
  });

  it("cannot be double-submitted while a withdrawal is in flight", () => {
    renderPrivacy({ busy: "model_egress" });
    expect(
      screen.getByTestId("withdraw-model_egress").hasAttribute("disabled"),
    ).toBe(true);
  });

  it("says undecided rather than guessing", () => {
    renderPrivacy({
      consents: [
        {
          consentType: "model_egress",
          label: "Gửi nội dung phiên tới mô hình",
          meaning: "…",
          decision: null,
        },
      ],
    });
    expect(
      screen.getByTestId("consent-decision-model_egress").textContent,
    ).toContain("Chưa quyết định");
  });
});


const TRASHED = {
  entity_type: "insight",
  entity_id: "insight-1",
  deleted_at: "2026-01-01T00:00:00Z",
  purge_after: "2026-01-31T00:00:00Z",
};

describe("taking the data out", () => {
  // `ExportService` existed and was well tested for months with no RPC and no
  // control anywhere in the app. The Coachee could read that their data was
  // theirs and do nothing whatsoever about it.
  it("offers a readable copy and a complete one", async () => {
    const props = renderPrivacy();
    await userEvent.click(screen.getByTestId("export-markdown"));
    expect(props.onExport).toHaveBeenCalledWith("markdown");
    await userEvent.click(screen.getByTestId("export-json"));
    expect(props.onExport).toHaveBeenCalledWith("json");
  });

  it("accepts no second export while one is running", () => {
    renderPrivacy({ busy: "export" });
    expect(screen.getByTestId("export-json").hasAttribute("disabled")).toBe(true);
  });
});

describe("the Trash", () => {
  it("says what deletion actually does when it is empty", () => {
    renderPrivacy();
    expect(screen.getByTestId("trash-empty").textContent).toContain(
      "trước khi mất hẳn",
    );
  });

  // The date is the whole promise. A Trash that does not show its deadline is
  // just a slower delete, and the Coachee cannot tell which one they are in.
  it("shows the date after which it cannot be undone", () => {
    renderPrivacy({ trash: [TRASHED] });
    const when = screen.getByTestId("trash-when-insight:insight-1");
    expect(when.textContent).toContain("2026-01-31");
    expect(when.textContent).not.toContain("T00:00:00Z");
  });

  it("names the kind of thing in words, not by its table", () => {
    renderPrivacy({ trash: [TRASHED] });
    expect(screen.getByTestId("trash-insight:insight-1").textContent).toContain(
      "Nhận thức",
    );
  });

  it("gets it back", async () => {
    const props = renderPrivacy({ trash: [TRASHED] });
    await userEvent.click(screen.getByTestId("restore-insight:insight-1"));
    expect(props.onRestore).toHaveBeenCalledWith("insight", "insight-1");
  });

  it("erases it for good, separately from restoring", async () => {
    const props = renderPrivacy({ trash: [TRASHED] });
    await userEvent.click(screen.getByTestId("purge-insight:insight-1"));
    expect(props.onPurge).toHaveBeenCalledWith("insight", "insight-1");
    expect(props.onRestore).not.toHaveBeenCalled();
  });

  it("accepts no second action on an item already working", () => {
    renderPrivacy({ trash: [TRASHED], busy: "insight:insight-1" });
    expect(
      screen.getByTestId("purge-insight:insight-1").hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen.getByTestId("restore-insight:insight-1").hasAttribute("disabled"),
    ).toBe(true);
  });
});


describe("what the product keeps", () => {
  // The transcript used to be deleted on a 90-day clock and now is not. A
  // Coachee deciding what to say in a session is owed that, and the versioned
  // disclosure is not the place for it — that states the encryption fact and
  // should not drift.
  it("says the conversation stays until the Coachee removes it", () => {
    renderPrivacy();
    expect(screen.getByTestId("privacy-retention").textContent).toContain(
      "cho tới khi bạn tự xoá",
    );
  });
});
