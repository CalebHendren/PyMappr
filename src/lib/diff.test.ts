import { describe, expect, it } from "vitest";
import { diffLines, diffStats, hunks, newSide, oldSide, splitLines, unifiedDiff } from "./diff";

function randomText(seed: number, n: number): string {
  let s = seed;
  const next = () => (s = (s * 1103515245 + 12345) % 2147483648);
  return Array.from({ length: n }, () => `line ${next() % 7}`).join("\n") + "\n";
}

describe("diffLines", () => {
  it("finds nothing between equal texts", () => {
    const d = diffLines("a\nb\n", "a\nb\n");
    expect(d.every((l) => l.kind === "same")).toBe(true);
    expect(hunks(d)).toEqual([]);
    expect(unifiedDiff("a\n", "a\n")).toBe("");
  });

  it("handles empty sides", () => {
    expect(diffLines("", "x\ny\n").map((l) => l.kind)).toEqual(["add", "add"]);
    expect(diffLines("x\n", "").map((l) => l.kind)).toEqual(["del"]);
    expect(splitLines("")).toEqual([]);
    expect(splitLines("a\r\nb")).toEqual(["a", "b"]);
  });

  it("finds a shortest edit", () => {
    // The classic example from Myers' paper: D = 5.
    const d = diffLines("A\nB\nC\nA\nB\nB\nA\n", "C\nB\nA\nB\nA\nC\n");
    expect(diffStats(d)).toEqual({ added: 2, removed: 3 });
  });

  it("numbers lines on both sides", () => {
    const d = diffLines("a\nb\nc\n", "a\nB\nc\nd\n");
    expect(d).toEqual([
      { kind: "same", text: "a", oldNo: 1, newNo: 1 },
      { kind: "del", text: "b", oldNo: 2, newNo: null },
      { kind: "add", text: "B", oldNo: null, newNo: 2 },
      { kind: "same", text: "c", oldNo: 3, newNo: 3 },
      { kind: "add", text: "d", oldNo: null, newNo: 4 },
    ]);
  });

  it("always rebuilds both texts", () => {
    for (let seed = 1; seed < 60; seed++) {
      const a = randomText(seed, 30 + (seed % 9));
      const b = randomText(seed * 7 + 3, 25 + (seed % 5));
      const d = diffLines(a, b);
      expect(oldSide(d)).toEqual(splitLines(a));
      expect(newSide(d)).toEqual(splitLines(b));
      // Never longer than deleting everything and adding everything.
      const { added, removed } = diffStats(d);
      expect(added + removed).toBeLessThanOrEqual(splitLines(a).length + splitLines(b).length);
    }
  });

  it("is fast enough for a whole script", () => {
    const a = Array.from({ length: 2000 }, (_, i) => `x${i} = ${i}`).join("\n");
    const b = a.replace("x500 = 500", "x500 = 501").replace("x1500 = 1500\n", "");
    const t = performance.now();
    const d = diffLines(a, b);
    expect(performance.now() - t).toBeLessThan(500);
    expect(diffStats(d)).toEqual({ added: 1, removed: 2 });
  });
});

describe("hunks and unified diffs", () => {
  const a = Array.from({ length: 20 }, (_, i) => `l${i + 1}`).join("\n") + "\n";

  it("writes diff -u output", () => {
    const b = a.replace("l5\n", "l5 changed\n").replace("l18\n", "");
    expect(unifiedDiff(a, b, "a.py", "b.py")).toBe(
      [
        "--- a.py",
        "+++ b.py",
        "@@ -2,7 +2,7 @@",
        " l2",
        " l3",
        " l4",
        "-l5",
        "+l5 changed",
        " l6",
        " l7",
        " l8",
        "@@ -15,6 +15,5 @@",
        " l15",
        " l16",
        " l17",
        "-l18",
        " l19",
        " l20",
        "",
      ].join("\n"),
    );
  });

  it("merges nearby changes into one hunk", () => {
    const b = a.replace("l5\n", "x\n").replace("l9\n", "y\n");
    const h = hunks(diffLines(a, b));
    expect(h).toHaveLength(1);
    expect([h[0].oldStart, h[0].oldLines, h[0].newStart, h[0].newLines]).toEqual([2, 11, 2, 11]);
  });

  it("starts an insertion at the top like diff -u", () => {
    expect(unifiedDiff("", "new\n")).toBe("--- original\n+++ suggested\n@@ -0,0 +1 @@\n+new\n");
  });
});
