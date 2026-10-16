import { describe, expect, it } from "vitest";

import { fmt, formatOverall } from "./format";

describe("formatOverall", () => {
  it("shows the score with its likely range", () => {
    expect(formatOverall({ median: 82, min: 78, max: 86, max_possible: 100 })).toBe("82/100, likely 78–86");
  });
  it("omits the range when it is a single value", () => {
    expect(formatOverall({ median: 90, min: 90, max: 90, max_possible: 100 })).toBe("90/100");
  });
  it("handles ungraded results", () => {
    expect(formatOverall({ median: null, min: null, max: null, max_possible: 100 })).toBe("Not graded");
  });
});

describe("fmt", () => {
  it("trims needless decimals", () => {
    expect([fmt(8), fmt(7.5), fmt(7.333), fmt(8.0)]).toEqual(["8", "7.5", "7.3", "8"]);
  });
});
