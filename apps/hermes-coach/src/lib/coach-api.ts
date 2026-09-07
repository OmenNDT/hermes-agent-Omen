/**
 * Typed client for the Coach loopback RPC.
 *
 * The server is authoritative for everything: gates, revisions, stage. This
 * client carries requests and routes replies, and deliberately holds no
 * derived coaching state — a client that computed a gate locally would show a
 * step advancing that the server never confirmed.
 *
 * Reads go through `call`. Mutations go through `mutate`, which attaches the
 * envelope the server requires: the session, the revision the caller believes
 * it is acting on, and an idempotency key so a retry after a dropped reply
 * cannot apply the command twice.
 */

const COACH_WS_PATH = "/api/coach/ws";

const LOOPBACK = "127.0.0.1";

export interface CoachApiOptions {
  port: number;
  token: string;
  /** Injectable so tests can drive the socket without a server. */
  createSocket?: (url: string) => WebSocket;
}

export class CoachRpcError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "CoachRpcError";
    this.code = code;
  }
}

export class CoachTransportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CoachTransportError";
  }
}

export interface MutateOptions {
  sessionId: string;
  revision: number;
  params?: Record<string, unknown>;
}

/** A mutation with its key already minted, so a retry reuses it. */
export interface PreparedCommand {
  method: string;
  params: Record<string, unknown>;
}

interface Pending {
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
}

export class CoachApi {
  private socket: WebSocket | null = null;
  private nextId = 1;
  private readonly pending = new Map<number, Pending>();

  private readonly options: CoachApiOptions;

  constructor(options: CoachApiOptions) {
    this.options = options;
  }

  connect(): Promise<void> {
    const url =
      `ws://${LOOPBACK}:${this.options.port}${COACH_WS_PATH}` +
      `?token=${encodeURIComponent(this.options.token)}`;
    const socket = (this.options.createSocket ?? ((target) => new WebSocket(target)))(
      url,
    );
    this.socket = socket;

    return new Promise<void>((resolve, reject) => {
      let settled = false;
      socket.onopen = () => {
        settled = true;
        resolve();
      };
      socket.onmessage = (event) => this.receive(String(event.data));
      socket.onclose = (event) => {
        const close = event as unknown as { code: number; reason: string };
        const detail = close.reason || `closed with code ${close.code}`;
        // A refused loopback check arrives as a close before open, so the
        // reason is the only diagnosis the user gets.
        if (!settled) {
          settled = true;
          reject(new CoachTransportError(detail));
        }
        this.failAllPending(new CoachTransportError(detail));
        this.socket = null;
      };
    });
  }

  disconnect(): void {
    this.socket?.close();
    this.socket = null;
  }

  /** A read. No envelope: nothing to make idempotent, nothing to stale. */
  call(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    return this.dispatch(method, params);
  }

  /** A mutation, with the envelope the server requires. */
  mutate(method: string, options: MutateOptions): Promise<unknown> {
    return this.send(this.prepare(method, options));
  }

  /**
   * Build a mutation without sending it.
   *
   * The key is minted here rather than per send, so retrying the same prepared
   * command is safe: the server recognises the key and replays its first
   * result instead of applying the command again.
   */
  prepare(method: string, options: MutateOptions): PreparedCommand {
    return {
      method,
      params: {
        ...(options.params ?? {}),
        session_id: options.sessionId,
        revision: options.revision,
        idempotency_key: newIdempotencyKey(),
      },
    };
  }

  send(command: PreparedCommand): Promise<unknown> {
    return this.dispatch(command.method, command.params);
  }

  /** Cancel one turn. Never a whole session. */
  cancel(sessionId: string, turnId: string): Promise<unknown> {
    return this.dispatch("coach.cancel", {
      session_id: sessionId,
      turn_id: turnId,
    });
  }

  private dispatch(
    method: string,
    params: Record<string, unknown>,
  ): Promise<unknown> {
    const socket = this.socket;
    if (!socket || socket.readyState !== 1) {
      return Promise.reject(
        new CoachTransportError("not connected to the Coach backend"),
      );
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }

  private receive(raw: string): void {
    const reply = JSON.parse(raw) as {
      id: number;
      result?: unknown;
      error?: { code: string; message: string };
    };
    const pending = this.pending.get(reply.id);
    if (!pending) return;
    this.pending.delete(reply.id);
    if (reply.error) {
      pending.reject(new CoachRpcError(reply.error.code, reply.error.message));
      return;
    }
    pending.resolve(reply.result);
  }

  private failAllPending(reason: CoachTransportError): void {
    for (const pending of this.pending.values()) pending.reject(reason);
    this.pending.clear();
  }
}

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
