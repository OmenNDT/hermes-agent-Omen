/**
 * In-process stand-in for the Coach WebSocket, for tests.
 *
 * Not MSW: MSW intercepts HTTP, and the Coach transport is a WebSocket
 * carrying JSON-RPC. A fake socket is both simpler and closer to the thing
 * being tested.
 *
 * It implements only what the client touches, and deliberately keeps every
 * message it received so a test can assert on the envelope the client built
 * rather than only on the answer it got back.
 */

export type RpcHandler = (
  method: string,
  params: Record<string, unknown>,
) => unknown;

export interface SentMessage {
  id: number | string;
  method: string;
  params: Record<string, unknown>;
}

/** The subset of WebSocket the client uses. */
export class FakeSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readyState = FakeSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;

  readonly sent: SentMessage[] = [];

  readonly url: string;
  private readonly handler: RpcHandler;

  constructor(url: string, handler: RpcHandler) {
    this.url = url;
    this.handler = handler;
  }

  /** Complete the handshake. Tests call this to control timing explicitly. */
  open(): void {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }

  send(raw: string): void {
    const request = JSON.parse(raw) as SentMessage;
    this.sent.push(request);
    let reply: Record<string, unknown>;
    try {
      reply = { id: request.id, result: this.handler(request.method, request.params) };
    } catch (error) {
      reply = {
        id: request.id,
        error: {
          code: (error as { code?: string }).code ?? "internal_error",
          message: (error as Error).message,
        },
      };
    }
    // Asynchronous like a real socket: a client that assumes a synchronous
    // reply would pass here and deadlock against the real server.
    queueMicrotask(() => this.onmessage?.({ data: JSON.stringify(reply) }));
  }

  close(code = 1000, reason = ""): void {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.({ code, reason });
  }

  /** Simulate the server closing, e.g. a failed loopback check. */
  serverClose(code: number, reason: string): void {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.({ code, reason });
  }
}

/** Raise a method-level failure with a stable code, as the server would. */
export function rpcFailure(code: string, message: string): Error {
  return Object.assign(new Error(message), { code });
}
