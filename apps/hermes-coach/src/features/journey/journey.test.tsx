import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { JourneyProps, JourneySession } from "./index";
import { Journey } from "./index";

afterEach(cleanup);

const SESSION: JourneySession = {
  id: "s1",
  started_at: "2026-02-01T09:00:00Z",
  ended_at: "2026-02-01T10:00:00Z",
  intention: "tìm bước đầu tiên",
  stage: "review",
  ended: true,
  safety_state: "normal",
  produced: { goals: 1, insights: 2, commitments: 0 },
  messages: 12,
  messages_ever: 12,
};

function renderJourney(overrides: Partial<JourneyProps> = {}) {
  const props: JourneyProps = {
    sessions: [SESSION],
    loading: false,
    error: null,
    openId: null,
    openTurns: null,
    openError: null,
    onOpen: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<Journey {...props} />);
  return props;
}

describe("before there is a history", () => {
  it("points at the only place a history comes from", () => {
    renderJourney({ sessions: [] });
    expect(
      screen.getByRole("link", { name: "mở một phiên" }).getAttribute("href"),
    ).toBe("#/coach");
  });

  it("distinguishes empty from not yet known", () => {
    renderJourney({ sessions: [], loading: true });
    expect(screen.getByTestId("journey-loading")).toBeTruthy();
    expect(screen.queryByTestId("journey-empty")).toBeNull();
  });

  it("reports a failure instead of an empty history", () => {
    renderJourney({ error: "internal_error: không đọc được" });
    expect(screen.getByTestId("journey-error").textContent).toContain(
      "internal_error",
    );
    expect(screen.queryByTestId("journey")).toBeNull();
  });
});

describe("a session in the history", () => {
  // A list of dates is an activity log — a metric about the person. What makes
  // a history worth opening is what each session left behind.
  it("says what the session produced", () => {
    renderJourney();
    expect(screen.getByTestId("journey-produced-s1").textContent).toBe(
      "1 mục tiêu · 2 nhận thức",
    );
  });

  it("omits what was not produced rather than showing a zero", () => {
    renderJourney();
    expect(screen.getByTestId("journey-produced-s1").textContent).not.toContain(
      "cam kết",
    );
  });

  it("shows the Coachee's own words for why they came", () => {
    renderJourney();
    expect(screen.getByTestId("journey-intention-s1").textContent).toContain(
      "tìm bước đầu tiên",
    );
  });

  it("shows the day, not the machine timestamp", () => {
    renderJourney();
    const when = screen.getByTestId("journey-when-s1").textContent ?? "";
    expect(when).toContain("2026-02-01");
    expect(when).not.toContain("T09:00:00Z");
  });

  it("says a finished session went the whole way", () => {
    renderJourney();
    expect(screen.getByTestId("journey-stage-s1").textContent).toBe(
      "Đi hết sáu bước",
    );
  });
});

describe("a session that did not finish", () => {
  const UNFINISHED: JourneySession = {
    ...SESSION,
    id: "s2",
    ended: false,
    ended_at: null,
    stage: "reality",
  };

  // Sitting with something and reaching no conclusion is a real hour of
  // coaching. Hiding those would teach the Coachee that only productive
  // sessions count.
  it("is shown, and named by where it stopped", () => {
    renderJourney({ sessions: [UNFINISHED] });
    expect(screen.getByTestId("journey-stage-s2").textContent).toBe(
      "Dừng ở Reality",
    );
    expect(screen.getByTestId("journey-when-s2").textContent).toContain(
      "chưa khép lại",
    );
  });

  it("says plainly when a session kept nothing", () => {
    renderJourney({
      sessions: [
        { ...UNFINISHED, produced: { goals: 0, insights: 0, commitments: 0 } },
      ],
    });
    expect(screen.getByTestId("journey-produced-s2").textContent).toBe(
      "Chưa lưu lại gì",
    );
  });
});

describe("a transcript that has aged out", () => {
  // Session rows are durable; the messages in them expire and are purged. The
  // entry stays real, and the screen must not offer words it no longer has.
  const AGED = { ...SESSION, messages: 0, messages_ever: 12 };

  it("says the conversation is gone rather than staying silent", () => {
    renderJourney({ sessions: [AGED] });
    expect(screen.getByTestId("journey-no-transcript-s1").textContent).toContain(
      "hết hạn lưu",
    );
  });

  it("still shows what that session produced", () => {
    renderJourney({ sessions: [AGED] });
    expect(screen.getByTestId("journey-produced-s1").textContent).toContain(
      "1 mục tiêu",
    );
  });

  // Caught on the first live run against real data: three sessions three days
  // old were reported as having lost their contents. They had been opened and
  // abandoned before the first turn. A false alarm about someone's own data is
  // worse than saying nothing at all.
  it("does not claim a loss when nothing was ever said", () => {
    renderJourney({
      sessions: [{ ...SESSION, messages: 0, messages_ever: 0 }],
    });
    expect(screen.queryByTestId("journey-no-transcript-s1")).toBeNull();
  });

  it("says nothing about expiry while the transcript is still there", () => {
    renderJourney();
    expect(screen.queryByTestId("journey-no-transcript-s1")).toBeNull();
  });
});


describe("reading a session back", () => {
  // Transcripts stopped expiring, and the Privacy screen says so — but until
  // now no screen could open one. Keeping someone's words forever somewhere
  // they can never read them carries the whole privacy cost of storage and
  // returns none of its value.
  it("offers to open one, saying how much is there", async () => {
    const props = renderJourney();
    const button = screen.getByTestId("journey-open-s1");
    expect(button.textContent).toContain("12");
    await userEvent.click(button);
    expect(props.onOpen).toHaveBeenCalledWith("s1");
  });

  it("offers nothing when there is nothing left to read", () => {
    renderJourney({ sessions: [{ ...SESSION, messages: 0, messages_ever: 12 }] });
    expect(screen.queryByTestId("journey-open-s1")).toBeNull();
  });

  it("shows the words with who said them", () => {
    renderJourney({
      openId: "s1",
      openTurns: [
        { id: "m1", voice: "coachee", content: "Tôi thấy bế tắc" },
        { id: "m2", voice: "coach", content: "Điều gì khiến vậy?" },
      ],
    });
    const list = screen.getByTestId("journey-transcript-s1");
    expect(list.textContent).toContain("Tôi thấy bế tắc");
    expect(screen.getByTestId("journey-turn-m1").textContent).toContain("Bạn");
    expect(screen.getByTestId("journey-turn-m2").textContent).toContain("Coach");
  });

  // A safety message that reads as coaching advice months later is the one
  // confusion this product cannot afford.
  it("keeps the Safety System distinguishable from the Coach", () => {
    renderJourney({
      openId: "s1",
      openTurns: [
        { id: "m1", voice: "safety_system", content: "Mình dừng phần coaching ở đây." },
      ],
    });
    expect(screen.getByTestId("journey-turn-m1").textContent).toContain("An toàn");
  });

  it("distinguishes still loading from an empty transcript", () => {
    renderJourney({ openId: "s1", openTurns: null });
    expect(screen.getByTestId("journey-transcript-loading")).toBeTruthy();
    expect(screen.queryByTestId("journey-transcript-s1")).toBeNull();
  });

  it("reports a failure instead of an empty conversation", () => {
    renderJourney({ openId: "s1", openError: "internal_error: không đọc được" });
    expect(screen.getByTestId("journey-transcript-error").textContent).toContain(
      "internal_error",
    );
  });

  it("closes again", async () => {
    const props = renderJourney({ openId: "s1", openTurns: [] });
    await userEvent.click(screen.getByTestId("journey-close-s1"));
    expect(props.onClose).toHaveBeenCalled();
  });
});
