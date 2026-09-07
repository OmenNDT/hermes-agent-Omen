import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Onboarding, type OnboardingProps } from "./index";
import {
  INITIAL_ONBOARDING,
  ONBOARDING_STEPS,
  canEnter,
  canGenerate,
  isComplete,
  nextStep,
  type OnboardingState,
} from "./steps";

const NOTE = "Dữ liệu Coach lưu trên máy này và không được mã hoá.";

afterEach(cleanup);

function state(overrides: Partial<OnboardingState> = {}): OnboardingState {
  return { ...INITIAL_ONBOARDING, ...overrides };
}

type ConsentHandler = OnboardingProps["onConsent"];

function setup(
  onConsent: ConsentHandler = vi.fn<ConsentHandler>(async () => "granted"),
) {
  const user = userEvent.setup();
  render(<Onboarding onConsent={onConsent} disclosureNote={NOTE} />);
  return { user, onConsent };
}

async function reachConsent(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Tôi đã hiểu và đồng ý" }));
  await user.click(screen.getByRole("button", { name: "Tôi đã đọc" }));
}

describe("step gating", () => {
  it("runs in the order the Coachee needs to decide", () => {
    expect([...ONBOARDING_STEPS]).toEqual([
      "agreement",
      "disclosure",
      "consent",
      "profile",
      "records",
    ]);
  });

  it("lets the agreement be entered first", () => {
    expect(canEnter("agreement", state())).toBe(true);
  });

  it("will not show the disclosure before the agreement", () => {
    expect(canEnter("disclosure", state())).toBe(false);
  });

  it("will not ask for consent before showing the disclosure", () => {
    // Consenting to storage you have not been told about is not consent.
    expect(canEnter("consent", state({ agreementAccepted: true }))).toBe(false);
  });

  it("asks for consent once both have happened", () => {
    expect(
      canEnter("consent", state({ agreementAccepted: true, disclosureSeen: true })),
    ).toBe(true);
  });

  it("advances only to a step that may be entered", () => {
    expect(nextStep("agreement", state())).toBeNull();
    expect(nextStep("agreement", state({ agreementAccepted: true }))).toBe(
      "disclosure",
    );
  });

  it("ends after the last step", () => {
    expect(nextStep("records", state())).toBeNull();
  });
});

describe("completion", () => {
  it("is not complete while a decision is missing", () => {
    expect(
      isComplete(
        state({
          agreementAccepted: true,
          disclosureSeen: true,
          localStorageConsent: "granted",
        }),
      ),
    ).toBe(false);
  });

  it("is complete once both decisions exist, either way", () => {
    // Declining is a decision. Onboarding must not loop until you say yes.
    expect(
      isComplete(
        state({
          agreementAccepted: true,
          disclosureSeen: true,
          localStorageConsent: "granted",
          modelEgressConsent: "declined",
        }),
      ),
    ).toBe(true);
  });

  it("allows generation only with granted egress", () => {
    expect(canGenerate(state({ modelEgressConsent: "granted" }))).toBe(true);
    expect(canGenerate(state({ modelEgressConsent: "declined" }))).toBe(false);
    expect(canGenerate(state({ localStorageConsent: "granted" }))).toBe(false);
  });
});

describe("agreement", () => {
  it("states the equal-companion stance", async () => {
    setup();
    expect(screen.getByText(/ngang vị thế/)).toBeTruthy();
  });

  it("states belief in the Coachee's own capacity", async () => {
    setup();
    expect(screen.getByText(/tiềm năng và năng lực tự giải quyết/)).toBeTruthy();
  });

  it("says it is neither advice nor therapy", async () => {
    setup();
    expect(screen.getByText(/không phải tư vấn và không phải trị liệu/)).toBeTruthy();
  });

  it("names the six steps", async () => {
    setup();
    expect(
      screen.getByText(/Pre-Coaching → Goal → Reality → Options → Will → Review/),
    ).toBeTruthy();
  });
});

describe("disclosure", () => {
  it("is not shown before the agreement is accepted", () => {
    setup();
    expect(screen.queryByTestId("step-disclosure")).toBeNull();
  });

  it("shows the unencrypted note the backend supplied", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Tôi đã hiểu và đồng ý" }));
    expect(screen.getByTestId("disclosure-note").textContent).toBe(NOTE);
  });

  it("comes before any consent control exists", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Tôi đã hiểu và đồng ý" }));
    expect(screen.queryByRole("button", { name: "Xác nhận" })).toBeNull();
  });
});

describe("consent", () => {
  it("offers a separate pair of buttons per decision", async () => {
    const { user } = setup();
    await reachConsent(user);
    expect(screen.getAllByRole("button", { name: "Xác nhận" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Từ chối" })).toHaveLength(2);
  });

  it("has no single control that accepts everything at once", async () => {
    const { user } = setup();
    await reachConsent(user);
    for (const button of screen.getAllByRole("button")) {
      expect(button.textContent?.toLowerCase()).not.toMatch(
        /tất cả|đồng ý hết|accept all/,
      );
    }
  });

  it("records the decision through a named UI control", async () => {
    const { user, onConsent } = setup();
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    expect(onConsent).toHaveBeenCalledWith(
      "local_storage",
      "confirm",
      "btn-local-confirm",
    );
  });

  it("sends decline through its own control id", async () => {
    const onConsent = vi.fn(async () => "declined" as const);
    const { user } = setup(onConsent);
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Từ chối" })[1]);
    expect(onConsent).toHaveBeenCalledWith(
      "model_egress",
      "decline",
      "btn-egress-decline",
    );
  });

  it("shows the decision the server settled on, not the click", async () => {
    // If the server declined what the UI sent, the UI must show declined.
    const onConsent = vi.fn(async () => "declined" as const);
    const { user } = setup(onConsent);
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    expect(screen.getByTestId("local-decision").textContent).toBe("Đã từ chối");
  });

  it("says what still works when egress is declined", async () => {
    const onConsent = vi.fn(async () => "declined" as const);
    const { user } = setup(onConsent);
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Từ chối" })[1]);
    expect(screen.getByTestId("egress-declined-note").textContent).toMatch(
      /vẫn dùng được mục tiêu/,
    );
  });

  it("does not offer to continue until both decisions exist", async () => {
    const { user } = setup();
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    expect(screen.queryByRole("button", { name: "Tiếp tục" })).toBeNull();
  });

  it("continues after a decline as readily as after a grant", async () => {
    const onConsent = vi
      .fn()
      .mockResolvedValueOnce("granted")
      .mockResolvedValueOnce("declined");
    const { user } = setup(onConsent);
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    await user.click(screen.getAllByRole("button", { name: "Từ chối" })[1]);
    expect(screen.getByRole("button", { name: "Tiếp tục" })).toBeTruthy();
  });

  it("tells the Coachee generation is unavailable after declining egress", async () => {
    const onConsent = vi
      .fn()
      .mockResolvedValueOnce("granted")
      .mockResolvedValueOnce("declined");
    const { user } = setup(onConsent);
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    await user.click(screen.getAllByRole("button", { name: "Từ chối" })[1]);
    await user.click(screen.getByRole("button", { name: "Tiếp tục" }));
    expect(screen.getByTestId("step-profile").textContent).toMatch(
      /tạm chưa dùng được/,
    );
  });
});

describe("accessibility", () => {
  it("labels the onboarding region", () => {
    setup();
    expect(screen.getByRole("region", { name: /Bắt đầu với Hermes Coach/ })).toBeTruthy();
  });

  it("groups each consent under its own legend", async () => {
    const { user } = setup();
    await reachConsent(user);
    expect(screen.getByRole("group", { name: /Lưu dữ liệu trên máy này/ })).toBeTruthy();
    expect(screen.getByRole("group", { name: /Gửi nội dung tới mô hình/ })).toBeTruthy();
  });

  it("reaches every consent control by keyboard alone", async () => {
    const { user } = setup();
    await reachConsent(user);
    const reached: string[] = [];
    for (let i = 0; i < 4; i += 1) {
      await user.tab();
      reached.push(document.activeElement?.textContent ?? "");
    }
    expect(reached).toEqual(["Xác nhận", "Từ chối", "Xác nhận", "Từ chối"]);
  });

  it("announces the declined-egress consequence as a status", async () => {
    const onConsent = vi.fn(async () => "declined" as const);
    const { user } = setup(onConsent);
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Từ chối" })[1]);
    expect(screen.getByRole("status")).toBeTruthy();
  });
});

describe("browser storage", () => {
  it("writes nothing while the Coachee decides", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { user } = setup();
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});

describe("records step", () => {
  const CANDIDATE = {
    id: "cand-1",
    kind: "goal",
    value: "Chuyển sang vai trò kiến trúc sư",
  };

  async function reachRecords(
    candidates = [CANDIDATE],
    onResolveCandidate = vi.fn(async () => {}),
    onCreateFirstGoal = vi.fn(),
  ) {
    const user = userEvent.setup();
    render(
      <Onboarding
        onConsent={vi.fn<ConsentHandler>(async () => "granted")}
        disclosureNote={NOTE}
        candidates={candidates}
        onResolveCandidate={onResolveCandidate}
        onCreateFirstGoal={onCreateFirstGoal}
      />,
    );
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[1]);
    await user.click(screen.getByRole("button", { name: "Tiếp tục" }));
    await user.click(
      screen.getByRole("button", { name: "Xem các mục cần xác nhận" }),
    );
    return { user, onResolveCandidate, onCreateFirstGoal };
  }

  it("is not reachable before consent is decided", async () => {
    const { user } = setup();
    await reachConsent(user);
    expect(screen.queryByTestId("step-records")).toBeNull();
  });

  it("shows a card for each pending candidate", async () => {
    await reachRecords([CANDIDATE, { id: "c2", kind: "insight", value: "x" }]);
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("resolves the card the Coachee acted on", async () => {
    const { user, onResolveCandidate } = await reachRecords();
    await user.click(screen.getByRole("button", { name: "Lưu" }));
    expect(onResolveCandidate).toHaveBeenCalledWith("cand-1", "accept", null);
  });

  it("does not ask about the first goal while records are pending", async () => {
    // Offering it here would invite skipping past undecided records.
    await reachRecords();
    expect(screen.queryByTestId("first-goal-prompt")).toBeNull();
  });

  it("asks about the first goal once nothing is left undecided", async () => {
    await reachRecords([]);
    expect(screen.getByTestId("first-goal-prompt")).toBeTruthy();
  });

  it("hands the first-goal decision back to the caller", async () => {
    const { user, onCreateFirstGoal } = await reachRecords([]);
    await user.click(screen.getByRole("button", { name: "Tạo mục tiêu đầu tiên" }));
    expect(onCreateFirstGoal).toHaveBeenCalledTimes(1);
  });

  it("renders no confirmation surface without a resolver", async () => {
    // A card with nothing behind its buttons would look actionable and not be.
    const user = userEvent.setup();
    render(
      <Onboarding
        onConsent={vi.fn<ConsentHandler>(async () => "granted")}
        disclosureNote={NOTE}
        candidates={[CANDIDATE]}
      />,
    );
    await reachConsent(user);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[0]);
    await user.click(screen.getAllByRole("button", { name: "Xác nhận" })[1]);
    await user.click(screen.getByRole("button", { name: "Tiếp tục" }));
    await user.click(
      screen.getByRole("button", { name: "Xem các mục cần xác nhận" }),
    );
    expect(screen.queryByRole("article")).toBeNull();
  });
});
