import { describe, expect, it, vi } from "vitest";

import type { CoachApi } from "@/lib/coach-api";
import {
  buildPrintDocument,
  fetchSessionExport,
  printDocument,
  type SessionExport,
} from "./export-pdf";

const EXPORT: SessionExport = {
  session_id: "s1",
  exported_at: "2026-09-17T07:00:00Z",
  profile_id: "local",
  disclosure: {
    encrypted_at_rest: false,
    note: "Bản xuất và cơ sở dữ liệu Coach không được mã hoá.",
    version: "2026-01",
  },
  turns: [
    { voice: "coachee", content: "Tôi muốn đổi vai trò.", stage: "goal", created_at: "2026-09-17T06:00:00Z" },
    { voice: "coach", content: "Điều gì khiến việc này quan trọng?", stage: "goal", created_at: "2026-09-17T06:01:00Z" },
  ],
  redacted_count: 0,
};

function withTurns(turns: SessionExport["turns"], extra: Partial<SessionExport> = {}) {
  return buildPrintDocument({ ...EXPORT, turns, ...extra });
}

describe("buildPrintDocument", () => {
  it("renders every turn", () => {
    const html = buildPrintDocument(EXPORT);
    expect(html).toContain("Tôi muốn đổi vai trò.");
    expect(html).toContain("Điều gì khiến việc này quan trọng?");
  });

  it("keeps the turns in the order the server sent them", () => {
    const html = buildPrintDocument(EXPORT);
    expect(html.indexOf("Tôi muốn đổi vai trò.")).toBeLessThan(
      html.indexOf("Điều gì khiến việc này quan trọng?"),
    );
  });

  it("labels who is speaking in Vietnamese", () => {
    const html = buildPrintDocument(EXPORT);
    expect(html).toContain("Bạn");
    expect(html).toContain("Coach");
  });

  it("carries the storage disclosure onto the page", () => {
    // The printed copy outlives the screen that explained the storage.
    expect(buildPrintDocument(EXPORT)).toContain("không được mã hoá");
  });

  it("names the moment it was exported", () => {
    expect(buildPrintDocument(EXPORT)).toContain("2026");
  });

  it("escapes markup in the transcript", () => {
    // The Coachee's own words reach an HTML document; a pasted tag must render
    // as text, not become part of the page.
    const html = withTurns([
      { voice: "coachee", content: "<script>alert(1)</script>", stage: "goal", created_at: "x" },
    ]);
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("escapes ampersands and quotes too", () => {
    const html = withTurns([
      { voice: "coachee", content: 'A & B "C"', stage: "goal", created_at: "x" },
    ]);
    expect(html).toContain("&amp;");
    expect(html).not.toContain('A & B "C"');
  });

  it("says when something was redacted", () => {
    // Silently removing part of the Coachee's own export is exactly the kind
    // of fact the privacy story must not hide.
    expect(withTurns(EXPORT.turns, { redacted_count: 2 })).toContain("2");
    expect(withTurns(EXPORT.turns, { redacted_count: 2 })).toMatch(/biên tập|redact/i);
  });

  it("does not mention redaction when nothing was redacted", () => {
    expect(buildPrintDocument(EXPORT)).not.toMatch(/biên tập/i);
  });

  it("says so when the transcript is empty rather than printing a blank page", () => {
    expect(withTurns([])).toMatch(/không còn|trống/i);
  });

  it("is a complete HTML document", () => {
    const html = buildPrintDocument(EXPORT);
    expect(html.trimStart().startsWith("<!doctype html")).toBe(true);
    expect(html).toContain("</html>");
  });

  it("sets the language to Vietnamese so the browser hyphenates correctly", () => {
    expect(buildPrintDocument(EXPORT)).toContain('lang="vi"');
  });
});

describe("fetchSessionExport", () => {
  it("asks the server for the session it was given", async () => {
    const call = vi.fn(async () => EXPORT);
    const api = { call } as unknown as CoachApi;
    await fetchSessionExport(api, "s1");
    expect(call).toHaveBeenCalledWith("coach.session.export", { session_id: "s1" });
  });

  it("returns what the server said", async () => {
    const api = { call: vi.fn(async () => EXPORT) } as unknown as CoachApi;
    expect((await fetchSessionExport(api, "s1")).session_id).toBe("s1");
  });
});


describe("printDocument", () => {
  // The blank-PDF bug lived here, not in the document builder. `onload` fired
  // once for the iframe's initial about:blank, so printing happened before the
  // real content was ever written. Every assertion below is about ordering.

  const HTML = buildPrintDocument(EXPORT);

  it("writes the document before the printer is called", () => {
    let seenAtPrint = "";
    printDocument(HTML, document, (view) => {
      seenAtPrint = view.document.body.textContent ?? "";
    });
    expect(seenAtPrint).toContain("Tôi muốn đổi vai trò.");
  });

  it("calls the printer exactly once", () => {
    const calls: number[] = [];
    printDocument(HTML, document, () => calls.push(1));
    expect(calls).toHaveLength(1);
  });

  it("prints the frame's own window, not the host page", () => {
    let printed: Window | null = null;
    printDocument(HTML, document, (view) => {
      printed = view;
    });
    expect(printed).not.toBe(window);
    expect(printed).not.toBeNull();
  });

  it("puts the disclosure in the printed document", () => {
    let text = "";
    printDocument(HTML, document, (view) => {
      text = view.document.body.textContent ?? "";
    });
    expect(text).toContain("không được mã hoá");
  });

  it("keeps the frame out of the accessibility tree", () => {
    printDocument(HTML, document, () => {});
    const frame = document.querySelector("iframe");
    expect(frame?.getAttribute("aria-hidden")).toBe("true");
  });

  it("keeps the frame until printing finishes", () => {
    // Removing it while the dialog is open cancels the print, which is a
    // second way to end up with no PDF.
    const before = document.querySelectorAll("iframe").length;
    printDocument(HTML, document, () => {});
    expect(document.querySelectorAll("iframe").length).toBe(before + 1);
  });

  it("drops the frame once the browser says printing is done", () => {
    const before = document.querySelectorAll("iframe").length;
    let view: Window | null = null;
    printDocument(HTML, document, (frameWindow) => {
      view = frameWindow;
    });
    view!.dispatchEvent(new Event("afterprint"));
    expect(document.querySelectorAll("iframe").length).toBe(before);
  });
});
