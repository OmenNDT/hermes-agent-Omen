import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Candidate, Turn } from "@/store/session";
import { CoachSession } from "./index";
import type { CoachSessionProps } from "./index";

afterEach(cleanup);

const TURNS: Turn[] = [
  { id: "t1-coachee", voice: "coachee", content: "Tôi muốn đổi việc." },
  { id: "t1-coach", voice: "coach", content: "Điều gì khiến bây giờ là lúc?" },
];

function renderSession(overrides: Partial<CoachSessionProps> = {}) {
  const props: CoachSessionProps = {
    started: true,
    connected: true,
    stage: "goal",
    confirmedSteps: ["pre_coaching"],
    safetyState: "normal",
    turns: TURNS,
    candidates: [],
    pendingTurnId: null,
    ended: false,
    error: null,
    note: null,
    gaps: [],
    resumable: null,
    onResume: vi.fn(),
    onStart: vi.fn(),
    onSend: vi.fn().mockResolvedValue(true),
    onCancel: vi.fn(),
    onResolveCandidate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<CoachSession {...props} />);
  return props;
}

describe("before a session exists", () => {
  it("offers to start one rather than an empty transcript", () => {
    renderSession({ started: false });
    expect(screen.getByTestId("coach-start")).toBeTruthy();
    expect(screen.queryByTestId("transcript")).toBeNull();
  });

  it("hands the intention to the caller, trimmed", async () => {
    const props = renderSession({ started: false });
    await userEvent.type(
      screen.getByLabelText(/dùng phiên này cho việc gì/i),
      "  rõ hướng đi  ",
    );
    await userEvent.click(screen.getByRole("button", { name: "Bắt đầu phiên" }));
    expect(props.onStart).toHaveBeenCalledWith("rõ hướng đi");
  });

  it("cannot open a session while the backend is unreachable", () => {
    renderSession({ started: false, connected: false });
    expect(
      screen.getByRole("button", { name: "Bắt đầu phiên" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(screen.getByTestId("coach-offline")).toBeTruthy();
  });
});

describe("during a session", () => {
  it("announces the latest Coach question as a live region", () => {
    renderSession();
    const region = screen.getByTestId("current-question");
    expect(region.getAttribute("aria-live")).toBe("polite");
    expect(region.textContent).toContain("Điều gì khiến bây giờ là lúc?");
  });

  it("shows the stage the server reported, not one it inferred", () => {
    renderSession({ stage: "reality" });
    expect(screen.getByTestId("stage-reality").getAttribute("aria-current")).toBe(
      "step",
    );
    expect(screen.getByTestId("stage-goal").getAttribute("aria-current")).toBeNull();
  });

  it("marks only the steps the server confirmed", () => {
    renderSession({ confirmedSteps: ["pre_coaching"] });
    expect(screen.getByTestId("stage-pre_coaching").textContent).toContain(
      "đã xác nhận",
    );
    expect(screen.getByTestId("stage-goal").textContent).not.toContain(
      "đã xác nhận",
    );
  });

  it("names who is speaking in words, not by colour alone", () => {
    renderSession();
    expect(screen.getByTestId("turn-t1-coach").textContent).toContain("Coach");
    expect(screen.getByTestId("turn-t1-coachee").textContent).toContain("Bạn");
  });

  it("sends the trimmed answer and clears the composer", async () => {
    const props = renderSession();
    const composer = screen.getByLabelText("Trả lời của bạn");
    await userEvent.type(composer, "  vì tôi đã chán  ");
    await userEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(props.onSend).toHaveBeenCalledWith("vì tôi đã chán");
    expect((composer as HTMLTextAreaElement).value).toBe("");
  });

  // A rejected turn writes nothing, so the same words can be sent again.
  // Without this the Coachee retypes what they just said because the model
  // produced a question that failed validation — their words, lost to our
  // problem.
  it("hands the answer back when the turn did not land", async () => {
    renderSession({ onSend: vi.fn().mockResolvedValue(false) });
    const composer = screen.getByLabelText("Trả lời của bạn");
    await userEvent.type(composer, "tôi thấy bế tắc");
    await userEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await waitFor(() =>
      expect((composer as HTMLTextAreaElement).value).toBe("tôi thấy bế tắc"),
    );
  });

  it("refuses to send an empty answer", async () => {
    const props = renderSession();
    await userEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("accepts no second message while a turn is in flight", () => {
    renderSession({ pendingTurnId: "turn-2" });
    expect(
      screen.getByRole("button", { name: "Gửi" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen.getByLabelText("Trả lời của bạn").hasAttribute("disabled"),
    ).toBe(true);
    expect(screen.getByTestId("coach-thinking")).toBeTruthy();
  });

  it("offers cancel only while a turn is in flight", async () => {
    expect(screen.queryByTestId("cancel-turn")).toBeNull();
    cleanup();
    const props = renderSession({ pendingTurnId: "turn-2" });
    await userEvent.click(screen.getByTestId("cancel-turn"));
    expect(props.onCancel).toHaveBeenCalled();
  });

  it("shows candidates for individual confirmation", () => {
    const candidates: Candidate[] = [
      { id: "c1", kind: "goal", value: "Đổi việc trước tháng 6" },
    ];
    renderSession({ candidates });
    expect(screen.getByTestId("value-c1").textContent).toBe(
      "Đổi việc trước tháng 6",
    );
  });

  it("reports a failure instead of swallowing it", () => {
    renderSession({ error: "provider_not_configured: chưa có mô hình" });
    expect(screen.getByTestId("coach-error").textContent).toContain(
      "provider_not_configured",
    );
  });
});

describe("safety", () => {
  const SAFETY_TURNS: Turn[] = [
    { id: "t2-coachee", voice: "coachee", content: "Tôi không muốn ở đây nữa" },
    {
      id: "t2-coach",
      voice: "safety_system",
      content: "Mình dừng phần coaching ở đây.",
    },
  ];

  it.each(["possible_crisis", "urgent"] as const)(
    "replaces coaching rather than sitting above a live composer (%s)",
    (safetyState) => {
      renderSession({ safetyState });
      expect(screen.getByTestId("coach-urgent")).toBeTruthy();
      expect(screen.queryByLabelText("Trả lời của bạn")).toBeNull();
      expect(screen.queryByRole("button", { name: "Gửi" })).toBeNull();
    },
  );

  it("shows the Safety System's own words, not the Coach's", () => {
    renderSession({ safetyState: "possible_crisis", turns: SAFETY_TURNS });
    expect(screen.getByTestId("safety-message").textContent).toContain(
      "Mình dừng phần coaching ở đây.",
    );
  });

  it("names the speaker so it cannot read as the Coach", () => {
    renderSession({ safetyState: "urgent", turns: SAFETY_TURNS });
    expect(screen.getByTestId("safety-voice").textContent).toBe("An toàn");
  });

  it("still shows what was said, so nothing disappears", () => {
    renderSession({ safetyState: "urgent", turns: SAFETY_TURNS });
    expect(screen.getByTestId("turn-t2-coachee")).toBeTruthy();
  });

  it("says something even if no safety message came through", () => {
    renderSession({ safetyState: "urgent", turns: [] });
    expect(screen.getByRole("alert").textContent).toContain("lý do an toàn");
  });

  it("keeps coaching while sensitive, and says it is going slower", () => {
    renderSession({ safetyState: "sensitive" });
    expect(screen.getByLabelText("Trả lời của bạn")).toBeTruthy();
    expect(screen.getByTestId("safety-sensitive")).toBeTruthy();
  });
});

describe("a session that has closed", () => {
  it("shows the transcript and no way to write into it", () => {
    renderSession({ ended: true });
    expect(screen.getByTestId("coach-ended")).toBeTruthy();
    expect(screen.getByTestId("transcript")).toBeTruthy();
    expect(screen.queryByLabelText("Trả lời của bạn")).toBeNull();
    expect(screen.queryByRole("button", { name: "Gửi" })).toBeNull();
  });

  it("points at what the session left behind", () => {
    renderSession({ ended: true });
    expect(
      screen.getByRole("link", { name: "Xem mục tiêu" }).getAttribute("href"),
    ).toBe("#/goals");
  });
});


describe("agreeing when nothing was asked", () => {
  // Twice in one live session the Coach closed with a phrasing the gate does
  // not accept, the Coachee answered "Đồng ý", and absolutely nothing happened
  // — no message, no step moving. Left unsaid, the only conclusion available to
  // them is that the app is broken.
  const NOTE =
    "Bạn vừa đồng ý, nhưng lúc này chưa có câu chốt bước nào đang mở nên bước chưa đóng.";

  it("says why the step did not close", () => {
    renderSession({ note: NOTE });
    expect(screen.getByTestId("coach-note").textContent).toContain(
      "chưa có câu chốt bước nào đang mở",
    );
  });

  it("is a status, not an alert: nothing failed", () => {
    renderSession({ note: NOTE });
    expect(screen.getByTestId("coach-note").getAttribute("role")).toBe("status");
    expect(screen.queryByTestId("coach-error")).toBeNull();
  });

  it("says nothing on an ordinary turn", () => {
    renderSession();
    expect(screen.queryByTestId("coach-note")).toBeNull();
  });
});


describe("an unfinished session waiting", () => {
  const RESUMABLE = {
    session_id: "s-old",
    started_at: "2026-08-28T09:00:00Z",
    intention: "tìm hướng đi",
    stage: "reality" as const,
  };

  // The id lived only in memory, so a reload put the session permanently out of
  // reach with every word still in the database. Thirteen of sixteen sessions
  // in a real profile read "chưa khép lại" — most lost, not abandoned.
  it("offers the session back with enough to recognise it", () => {
    renderSession({ started: false, resumable: RESUMABLE });
    const detail = screen.getByTestId("coach-resume-detail").textContent ?? "";
    expect(detail).toContain("2026-08-28");
    expect(detail).toContain("Reality");
    expect(detail).toContain("tìm hướng đi");
  });

  // Not adopting it silently was a deliberate call and it stands: the Coachee
  // decides whether to go back into a half-finished conversation.
  it("offers rather than assumes", async () => {
    const props = renderSession({ started: false, resumable: RESUMABLE });
    expect(screen.getByTestId("coach-start")).toBeTruthy();
    expect(props.onResume).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("coach-resume-open"));
    expect(props.onResume).toHaveBeenCalled();
  });

  it("says starting fresh does not throw the old one away", () => {
    renderSession({ started: false, resumable: RESUMABLE });
    expect(screen.getByTestId("coach-resume").textContent).toContain(
      "vẫn được giữ nguyên",
    );
  });

  it("offers nothing while the backend is unreachable", () => {
    renderSession({ started: false, connected: false, resumable: RESUMABLE });
    expect(screen.queryByTestId("coach-resume")).toBeNull();
  });

  it("says nothing when there is nothing to return to", () => {
    renderSession({ started: false });
    expect(screen.queryByTestId("coach-resume")).toBeNull();
  });
});


describe("what the step has not covered", () => {
  // The six steps rested entirely on the closing gate — an explicit yes to a
  // well-formed question — with nothing checking the step had any content.
  // `stage_is_complete` was written for that job and never wired, because
  // nothing populated the snapshots it reads.
  it("names the gaps rather than judging the step", () => {
    renderSession({ gaps: ["mốc thời gian", "mức cam kết 1–10"] });
    const said = screen.getByTestId("coach-gaps").textContent ?? "";
    expect(said).toContain("mốc thời gian");
    expect(said).toContain("mức cam kết 1–10");
  });

  // Shown, not enforced: the server still lets the step close. Wording it as a
  // failure would be a second opinion the database does not hold.
  it("is a status, and leaves the composer alone", () => {
    renderSession({ gaps: ["mốc thời gian"] });
    expect(screen.getByTestId("coach-gaps").getAttribute("role")).toBe("status");
    expect(screen.getByLabelText("Trả lời của bạn")).toBeTruthy();
  });

  it("says nothing when the step has what it needs", () => {
    renderSession({ gaps: [] });
    expect(screen.queryByTestId("coach-gaps")).toBeNull();
  });
});
