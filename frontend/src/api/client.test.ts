import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("returns parsed JSON", async () => {
    mockFetch(200, { status: "ok", database: "ok" });
    expect(await api.health()).toEqual({ status: "ok", database: "ok" });
  });

  it("surfaces a string detail from the server", async () => {
    mockFetch(409, { detail: "Confirm the rubric before grading." });
    await expect(api.gradeSubmission(1)).rejects.toMatchObject({ status: 409, message: "Confirm the rubric before grading." });
  });

  it("flattens FastAPI validation errors", async () => {
    mockFetch(422, { detail: [{ loc: ["body", "criteria"], msg: "List should have at least 1 item" }] });
    await expect(api.confirmRubric(1, { criteria: [] })).rejects.toThrow("criteria: List should have at least 1 item");
  });

  it("calls the same-origin /api path by default", async () => {
    mockFetch(200, { status: "ok", database: "ok" });
    await api.health();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/health");
  });

  it("explains when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.health().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toMatch(/Could not reach the server/);
  });
});
