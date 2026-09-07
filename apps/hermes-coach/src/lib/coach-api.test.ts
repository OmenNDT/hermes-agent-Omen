import { beforeEach, describe, expect, it, vi } from "vitest";

import { CoachApi, CoachRpcError, CoachTransportError } from "./coach-api";
import { FakeSocket, rpcFailure, type RpcHandler } from "./fake-rpc";

const TOKEN = "t".repeat(32);

function build(handler: RpcHandler = () => ({ ok: true })) {
  let socket!: FakeSocket;
  const api = new CoachApi({
    port: 8731,
    token: TOKEN,
    createSocket: (url) => {
      socket = new FakeSocket(url, handler);
      return socket as unknown as WebSocket;
    },
  });
  return { api, socket: () => socket };
}

async function connected(handler?: RpcHandler) {
  const built = build(handler);
  const ready = built.api.connect();
  built.socket().open();
  await ready;
  return built;
}

describe("connection", () => {
  it("addresses the Coach endpoint on loopback with the token", async () => {
    const { socket } = await connected();
    const url = new URL(socket().url);
    expect(url.protocol).toBe("ws:");
    expect(url.hostname).toBe("127.0.0.1");
    expect(url.port).toBe("8731");
    expect(url.pathname).toBe("/api/coach/ws");
    expect(url.searchParams.get("token")).toBe(TOKEN);
  });

  it("never puts the token anywhere but the query string", async () => {
    // The backend reads it from there; duplicating it into a header or body
    // would widen where a token can be observed for no benefit.
    const { socket } = await connected();
    for (const message of socket().sent) {
      expect(JSON.stringify(message)).not.toContain(TOKEN);
    }
  });

  it("resolves connect only once the socket is open", async () => {
    const { api, socket } = build();
    let opened = false;
    const ready = api.connect().then(() => {
      opened = true;
    });
    expect(opened).toBe(false);
    socket().open();
    await ready;
    expect(opened).toBe(true);
  });

  it("reports a refused handshake as a transport error", async () => {
    const { api, socket } = build();
    const ready = api.connect();
    socket().serverClose(1008, "token does not match this session");
    await expect(ready).rejects.toBeInstanceOf(CoachTransportError);
  });

  it("surfaces the close reason so a bad token is diagnosable", async () => {
    const { api, socket } = build();
    const ready = api.connect();
    socket().serverClose(1008, "token does not match this session");
    await expect(ready).rejects.toThrow(/token/);
  });
});

describe("calling", () => {
  it("returns the result of a read", async () => {
    const { api } = await connected((method) =>
      method === "coach.today" ? { goals: 2 } : {},
    );
    await expect(api.call("coach.today")).resolves.toEqual({ goals: 2 });
  });

  it("gives every request a distinct id", async () => {
    const { api, socket } = await connected();
    await Promise.all([api.call("coach.today"), api.call("coach.today")]);
    const ids = socket().sent.map((message) => message.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("routes each reply to its own caller", async () => {
    const { api } = await connected((_method, params) => ({ echo: params.n }));
    const [first, second] = await Promise.all([
      api.call("coach.echo", { n: 1 }),
      api.call("coach.echo", { n: 2 }),
    ]);
    expect(first).toEqual({ echo: 1 });
    expect(second).toEqual({ echo: 2 });
  });

  it("rejects with the server's stable error code", async () => {
    const { api } = await connected(() => {
      throw rpcFailure("stale_revision", "session is at 3");
    });
    await expect(api.call("coach.rename")).rejects.toBeInstanceOf(CoachRpcError);
    await expect(api.call("coach.rename")).rejects.toMatchObject({
      code: "stale_revision",
    });
  });

  it("refuses to call before the socket is open", async () => {
    const { api } = build();
    await expect(api.call("coach.today")).rejects.toBeInstanceOf(
      CoachTransportError,
    );
  });

  it("fails pending calls when the socket closes under them", async () => {
    const { api, socket } = await connected(() => {
      throw new Error("never answered");
    });
    const pending = api.call("coach.today");
    socket().serverClose(1006, "connection lost");
    await expect(pending).rejects.toBeInstanceOf(CoachTransportError);
  });
});

describe("mutating commands", () => {
  it("carries session, revision and an idempotency key", async () => {
    const { api, socket } = await connected();
    await api.mutate("coach.rename", {
      sessionId: "session-1",
      revision: 3,
      params: { title: "Mục tiêu" },
    });
    const sent = socket().sent[0];
    expect(sent.params).toMatchObject({
      session_id: "session-1",
      revision: 3,
      title: "Mục tiêu",
    });
    expect(typeof sent.params.idempotency_key).toBe("string");
  });

  it("mints a different key per command", async () => {
    const { api, socket } = await connected();
    await api.mutate("coach.rename", { sessionId: "s", revision: 0, params: {} });
    await api.mutate("coach.rename", { sessionId: "s", revision: 1, params: {} });
    const [first, second] = socket().sent.map((m) => m.params.idempotency_key);
    expect(first).not.toBe(second);
  });

  it("reuses the key when the same command is retried", async () => {
    // The point of the key: a retry after a dropped reply must not apply twice.
    const { api, socket } = await connected();
    const command = api.prepare("coach.rename", {
      sessionId: "s",
      revision: 0,
      params: {},
    });
    await api.send(command);
    await api.send(command);
    const [first, second] = socket().sent.map((m) => m.params.idempotency_key);
    expect(first).toBe(second);
  });

  it("does not attach an envelope to a read", async () => {
    const { api, socket } = await connected();
    await api.call("coach.today");
    expect(socket().sent[0].params).not.toHaveProperty("idempotency_key");
    expect(socket().sent[0].params).not.toHaveProperty("revision");
  });
});

describe("cancellation", () => {
  it("sends a cancel for one turn", async () => {
    const { api, socket } = await connected(() => ({ cancelled: true }));
    await api.cancel("session-1", "turn-1");
    expect(socket().sent[0]).toMatchObject({
      method: "coach.cancel",
      params: { session_id: "session-1", turn_id: "turn-1" },
    });
  });
});

describe("what the client must never do", () => {
  let api: CoachApi;

  beforeEach(async () => {
    ({ api } = await connected());
  });

  it("exposes no way to confirm records in bulk", () => {
    const surface = Object.getOwnPropertyNames(Object.getPrototypeOf(api));
    for (const name of surface) {
      expect(name.toLowerCase()).not.toContain("batch");
      expect(name.toLowerCase()).not.toContain("bulk");
      expect(name.toLowerCase()).not.toMatch(/confirmall|acceptall/);
    }
  });

  it("writes nothing to browser storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    await api.call("coach.today");
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});
