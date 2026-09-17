/**
 * Print one session's transcript, which is how it becomes a PDF.
 *
 * The browser's own print-to-PDF does the conversion. Generating the PDF on
 * the server would mean shipping a page-layout engine and a Vietnamese-capable
 * font to solve a problem every browser already solves correctly, and it would
 * take the choice of filename and location away from the person saving it.
 *
 * The document is built as a standalone HTML string rather than by restyling
 * the app: a print stylesheet over the live page would carry the navigation,
 * the connection banner and whatever else happened to be on screen into the
 * saved file.
 */

import type { CoachApi } from "@/lib/coach-api";

export interface SessionExportTurn {
  voice: string;
  content: string;
  stage: string | null;
  created_at: string;
}

export interface SessionExport {
  session_id: string;
  exported_at: string;
  profile_id: string;
  disclosure: { encrypted_at_rest: boolean; note: string; version: string };
  turns: SessionExportTurn[];
  /** How many lines the server removed as credential-shaped. */
  redacted_count: number;
}

const VOICE_LABELS: Record<string, string> = {
  coach: "Coach",
  coachee: "Bạn",
  product_ui: "Hệ thống",
  safety_system: "Hệ thống an toàn",
};

export function fetchSessionExport(
  api: CoachApi,
  sessionId: string,
): Promise<SessionExport> {
  return api.call("coach.session.export", {
    session_id: sessionId,
  }) as Promise<SessionExport>;
}

/** The Coachee's own words reach an HTML document; a pasted tag must stay text. */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatMoment(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("vi-VN");
}

export function buildPrintDocument(payload: SessionExport): string {
  const turns = payload.turns
    .map(
      (turn) => `
      <li class="turn ${turn.voice === "coach" ? "coach" : "coachee"}">
        <p class="who">${escapeHtml(VOICE_LABELS[turn.voice] ?? turn.voice)}</p>
        <p class="said">${escapeHtml(turn.content)}</p>
      </li>`,
    )
    .join("");

  const body = payload.turns.length
    ? `<ol class="turns">${turns}</ol>`
    : `<p class="empty">Phiên này không còn lượt nào để in.</p>`;

  // Stated, not silently applied: "we removed part of your own export" is not
  // a fact to hide in a file the Coachee keeps.
  const redaction = payload.redacted_count
    ? `<p class="note">Đã biên tập ${payload.redacted_count} dòng trông giống thông tin xác thực.</p>`
    : "";

  return `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Phiên coaching ${escapeHtml(payload.session_id)}</title>
<style>
  @page { margin: 2cm; }
  body { font-family: "Times New Roman", serif; font-size: 12pt; line-height: 1.5; color: #000; }
  h1 { font-size: 16pt; margin: 0 0 .2cm; }
  .meta { font-size: 10pt; color: #333; margin: 0 0 .1cm; }
  .disclosure { font-size: 9pt; color: #444; border: 1pt solid #999; padding: .3cm; margin: .5cm 0; }
  .note { font-size: 9pt; color: #444; }
  .turns { list-style: none; padding: 0; margin: .6cm 0 0; }
  /* A turn must not be split across pages: half a question on each side of a
     page break is harder to read than a slightly shorter page. */
  .turn { margin: 0 0 .45cm; page-break-inside: avoid; }
  .who { font-weight: bold; margin: 0; font-size: 10pt; }
  .coach .who { color: #222; }
  .coachee .who { color: #555; }
  .said { margin: .1cm 0 0; white-space: pre-wrap; }
  .empty { font-style: italic; }
</style>
</head>
<body>
  <h1>Phiên coaching</h1>
  <p class="meta">Mã phiên: ${escapeHtml(payload.session_id)}</p>
  <p class="meta">Xuất lúc: ${escapeHtml(formatMoment(payload.exported_at))}</p>
  <div class="disclosure">${escapeHtml(payload.disclosure.note)}</div>
  ${redaction}
  ${body}
</body>
</html>`;
}

/** Hands the finished frame to the browser. Replaced in tests. */
export type Printer = (view: Window) => void;

const printWindow: Printer = (view) => {
  view.focus();
  view.print();
};

/**
 * Render the document in a hidden frame and open the print dialog.
 *
 * A frame rather than `window.open`: a popup blocker can refuse a new window,
 * and the app page stays exactly as the Coachee left it.
 *
 * The document is written synchronously rather than through `srcdoc`, because
 * `srcdoc` loads asynchronously while appending the frame fires `load` for its
 * initial `about:blank` straight away. Printing on that first event produced a
 * blank PDF: the dialog opened on an empty document and the real content
 * arrived afterwards. There is nothing to wait for here — the page carries its
 * own CSS inline and loads no images or fonts — so writing it in one go removes
 * the race instead of trying to win it.
 */
export function printDocument(
  html: string,
  doc: Document = document,
  printer: Printer = printWindow,
): void {
  const frame = doc.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.setAttribute("title", "Bản in phiên coaching");
  // Off-screen rather than zero-sized: a frame with no box has nothing to lay
  // out, and some browsers print exactly that.
  frame.style.position = "fixed";
  frame.style.left = "-10000px";
  frame.style.top = "0";
  frame.style.width = "210mm";
  frame.style.height = "297mm";
  frame.style.border = "0";
  doc.body.appendChild(frame);

  const inner = frame.contentDocument;
  const view = frame.contentWindow;
  if (!inner || !view) {
    frame.remove();
    return;
  }

  inner.open();
  inner.write(html);
  inner.close();

  try {
    printer(view);
  } finally {
    // After the dialog, not during it: removing the frame while the browser is
    // still reading the document cancels the print. `afterprint` is the signal
    // for that; the timeout is the fallback for a browser that never sends it.
    const drop = () => frame.remove();
    view.addEventListener?.("afterprint", drop, { once: true });
    setTimeout(drop, 60_000);
  }
}

export async function exportSessionAsPdf(
  api: CoachApi,
  sessionId: string,
): Promise<void> {
  printDocument(buildPrintDocument(await fetchSessionExport(api, sessionId)));
}
