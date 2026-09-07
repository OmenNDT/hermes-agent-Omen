/**
 * Where the page gets its port and token.
 *
 * The launcher prints a URL carrying both, and the browser is opened on it.
 * They are read from `window.location` and held in memory only: writing the
 * token to `localStorage` would outlive the process that minted it and turn a
 * per-run secret into a stored one.
 */

import { CoachApi } from "./coach-api";

export interface Handshake {
  port: number;
  token: string;
}

export class MissingHandshake extends Error {
  constructor() {
    super("no token in the page URL; open Coach from the link the launcher printed");
    this.name = "MissingHandshake";
  }
}

export function readHandshake(location: {
  search: string;
  port: string;
}): Handshake {
  const token = new URLSearchParams(location.search).get("token");
  if (!token) throw new MissingHandshake();
  const port = Number(location.port);
  if (!Number.isInteger(port) || port <= 0) throw new MissingHandshake();
  return { port, token };
}

let api: CoachApi | null = null;

/** The one client for this page. */
export function coachApi(): CoachApi {
  if (!api) throw new Error("Coach API not connected yet");
  return api;
}

export async function connectCoach(handshake: Handshake): Promise<CoachApi> {
  api = new CoachApi(handshake);
  await api.connect();
  return api;
}

/** Test seam: install a client without a real socket. */
export function setCoachApiForTest(client: CoachApi | null): void {
  api = client;
}
