import { describe, expect, it, vi } from "vitest";

import type { CoachApi } from "@/lib/coach-api";
import { resolveCandidate } from "./resolve-candidate";

type Call = (method: string, params?: Record<string, unknown>) => Promise<unknown>;

function fakeApi(
  onCall: ReturnType<typeof vi.fn<Call>> = vi.fn<Call>(async () => ({
    intent_token: "tok",
  })),
) {
  return { api: { call: onCall } as unknown as CoachApi, onCall };
}

describe("resolveCandidate", () => {
  it("mints before it confirms", async () => {
    const { api, onCall } = fakeApi();
    await resolveCandidate(api, "s1", "c1", "accept", null);
    expect(onCall.mock.calls.map((call) => call[0])).toEqual([
      "coach.candidate.intent",
      "coach.candidate.confirm",
    ]);
  });

  it("binds the same action to both calls", async () => {
    const { api, onCall } = fakeApi();
    await resolveCandidate(api, "s1", "c1", "discard", null);
    expect(onCall.mock.calls[0][1]).toMatchObject({ action: "discard" });
    expect(onCall.mock.calls[1][1]).toMatchObject({ action: "discard" });
  });

  it("binds the same edited value to both calls", async () => {
    // A mismatch is what the server refuses, so the client must not create one.
    const { api, onCall } = fakeApi();
    await resolveCandidate(api, "s1", "c1", "edit", "bản sửa");
    expect(onCall.mock.calls[0][1]).toMatchObject({ edited_value: "bản sửa" });
    expect(onCall.mock.calls[1][1]).toMatchObject({ edited_value: "bản sửa" });
  });

  it("passes the freshly minted token to the confirmation", async () => {
    const onCall = vi.fn<Call>(async () => ({ intent_token: "minted-123" }));
    const { api } = fakeApi(onCall);
    await resolveCandidate(api, "s1", "c1", "accept", null);
    expect(onCall.mock.calls[1][1]).toMatchObject({ intent_token: "minted-123" });
  });

  it("uses a fresh command id per attempt", async () => {
    const { api, onCall } = fakeApi();
    await resolveCandidate(api, "s1", "c1", "accept", null);
    await resolveCandidate(api, "s1", "c1", "accept", null);
    const first = onCall.mock.calls[1][1] as Record<string, unknown>;
    const second = onCall.mock.calls[3][1] as Record<string, unknown>;
    expect(first.command_id).not.toBe(second.command_id);
  });

  it("does not confirm when minting is refused", async () => {
    const onCall = vi.fn<Call>(async () => {
      throw new Error("candidate is already resolved");
    });
    const { api } = fakeApi(onCall);
    await expect(
      resolveCandidate(api, "s1", "c1", "accept", null),
    ).rejects.toThrow(/already resolved/);
    expect(onCall).toHaveBeenCalledTimes(1);
  });
});
