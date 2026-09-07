import { describe, expect, it } from "vitest";

import { MissingHandshake, readHandshake } from "./connection";

describe("handshake", () => {
  it("reads the port and token the launcher put in the URL", () => {
    expect(
      readHandshake({ search: "?token=abc123", port: "8912" }),
    ).toEqual({ port: 8912, token: "abc123" });
  });

  it("refuses a page opened without a token", () => {
    // Opening 127.0.0.1:port by hand must not silently produce a broken client.
    expect(() => readHandshake({ search: "", port: "8912" })).toThrow(
      MissingHandshake,
    );
  });

  it("refuses a location with no port", () => {
    expect(() => readHandshake({ search: "?token=abc", port: "" })).toThrow(
      MissingHandshake,
    );
  });

  it("says how to recover", () => {
    try {
      readHandshake({ search: "", port: "8912" });
    } catch (error) {
      expect((error as Error).message).toMatch(/link the launcher printed/);
    }
  });

  it("keeps the token out of any storage", () => {
    // Held in memory for the life of the page; a stored token would outlive the
    // process that minted it.
    const before = { ...localStorage };
    readHandshake({ search: "?token=abc123", port: "8912" });
    expect({ ...localStorage }).toEqual(before);
  });
});
