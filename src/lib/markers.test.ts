import { describe, expect, it } from "vitest";
import { MARKER_NAMES, areaToSize, markerCode, markerPath, markerPathAt, markerShape } from "./markers";

describe("markers", () => {
  it("names every shape solid and open, as PyMappr does", () => {
    expect(MARKER_NAMES).toHaveLength(30);
    expect(MARKER_NAMES.slice(0, 3)).toEqual(["Circle", "Square", "Triangle"]);
    expect(markerCode("Star (open)")).toBe("*");
    expect(markerCode("P")).toBe("P");
    expect(markerCode("nonsense")).toBe("o");
  });

  it("scales matplotlib's unit shapes", () => {
    expect(markerPathAt("Square", 10, 100, 50)).toBe("M95 55L105 55L105 45L95 45Z");
    expect(markerPathAt("Triangle", 2)).toBe("M0 -1L-1 1L1 1Z");
    expect(markerPath("s")).toBe("M-1 1L1 1L1 -1L-1 -1Z");
    expect(markerPath("Diamond (open)")).toBe(markerPath("D"));
    expect(markerShape("Star").join).toBe("bevel");
  });

  it("draws a scatter area as a √s-point marker", () => {
    expect(areaToSize(30)).toBeCloseTo(5.477, 3);
  });
});
