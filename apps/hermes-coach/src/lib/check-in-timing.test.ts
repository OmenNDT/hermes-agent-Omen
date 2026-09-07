import { describe, expect, it } from "vitest";

import { day, describeTiming } from "./check-in-timing";

/**
 * Home used to render a check-in's raw `scheduled_at` under a heading that said
 * "Cần bạn hôm nay", for an item fourteen days away. Both halves were wrong:
 * the heading claimed urgency the row did not have, and the row said
 * "2026-09-13T14:39:45Z", which is not a sentence.
 */
describe("saying when a check-in is", () => {
  const at = (due: boolean, days_until: number | null) => ({
    due,
    days_until,
    scheduled_at: "2026-01-15T00:00:00Z",
  });

  it("says it has arrived, without pretending to a date", () => {
    expect(describeTiming(at(true, 0))).toBe("Đã tới hẹn nhìn lại");
  });

  it("counts how far past the day it is", () => {
    expect(describeTiming(at(true, -1))).toBe("Quá hẹn 1 ngày");
    expect(describeTiming(at(true, -5))).toBe("Quá hẹn 5 ngày");
  });

  // The distinction the whole change exists for: something still coming must
  // never read as something needing them now.
  it("says how long is left when it has not arrived", () => {
    expect(describeTiming(at(false, 14))).toBe("Còn 14 ngày");
  });

  it("says tomorrow rather than 'còn 1 ngày'", () => {
    expect(describeTiming(at(false, 1))).toBe("Ngày mai");
  });

  it("falls back to the date when the server sent no count", () => {
    expect(describeTiming(at(false, null))).toBe("Hẹn nhìn lại 2026-01-15");
  });

  it("shows the day without the machine timestamp around it", () => {
    expect(day("2026-09-13T14:39:45Z")).toBe("2026-09-13");
  });
});
