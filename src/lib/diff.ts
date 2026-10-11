// Line diffs for reviewing a revised script: Myers' O(ND) algorithm over
// lines, grouped into unified-diff hunks.

export type DiffLine = {
  kind: "same" | "add" | "del";
  text: string;
  /** 1-based line numbers in the old and new text (null where absent). */
  oldNo: number | null;
  newNo: number | null;
};

export type Hunk = {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: DiffLine[];
};

/** Lines of a text; a final newline does not start another line. */
export function splitLines(text: string): string[] {
  if (text === "") return [];
  const lines = text.split(/\r?\n/);
  if (lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** The edit script turning `a` into `b`, line by line (Myers 1986, with the
 * common head and tail trimmed first). */
export function diffLines(oldText: string, newText: string): DiffLine[] {
  const a = splitLines(oldText);
  const b = splitLines(newText);
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head++;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
  const midA = a.slice(head, a.length - tail);
  const midB = b.slice(head, b.length - tail);

  const ops = myers(midA, midB);
  const out: DiffLine[] = [];
  for (let k = 0; k < head; k++) out.push({ kind: "same", text: a[k], oldNo: k + 1, newNo: k + 1 });
  let i = head;
  let j = head;
  for (const op of ops) {
    if (op === "same") {
      out.push({ kind: "same", text: a[i], oldNo: i + 1, newNo: j + 1 });
      i++;
      j++;
    } else if (op === "del") {
      out.push({ kind: "del", text: a[i], oldNo: i + 1, newNo: null });
      i++;
    } else {
      out.push({ kind: "add", text: b[j], oldNo: null, newNo: j + 1 });
      j++;
    }
  }
  for (let k = 0; k < tail; k++) {
    out.push({ kind: "same", text: a[i], oldNo: i + 1, newNo: j + 1 });
    i++;
    j++;
  }
  return out;
}

type Op = "same" | "add" | "del";

function myers(a: string[], b: string[]): Op[] {
  const n = a.length;
  const m = b.length;
  if (n === 0) return Array<Op>(m).fill("add");
  if (m === 0) return Array<Op>(n).fill("del");
  const max = n + m;
  const offset = max;
  const v = new Int32Array(2 * max + 2);
  const trace: Int32Array[] = [];
  let found = false;
  for (let d = 0; d <= max && !found; d++) {
    trace.push(v.slice());
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? v[offset + k + 1] : v[offset + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) {
        x++;
        y++;
      }
      v[offset + k] = x;
      if (x >= n && y >= m) {
        found = true;
        break;
      }
    }
  }
  // Walk the trace back from (n, m).
  const ops: Op[] = [];
  let x = n;
  let y = m;
  for (let d = trace.length - 1; d > 0; d--) {
    const vd = trace[d];
    const k = x - y;
    const prevK = k === -d || (k !== d && vd[offset + k - 1] < vd[offset + k + 1]) ? k + 1 : k - 1;
    const prevX = vd[offset + prevK];
    const prevY = prevX - prevK;
    while (x > prevX && y > prevY) {
      ops.push("same");
      x--;
      y--;
    }
    ops.push(prevK === k + 1 ? "add" : "del");
    x = prevX;
    y = prevY;
  }
  while (x > 0 && y > 0) {
    ops.push("same");
    x--;
    y--;
  }
  return ops.reverse();
}

/** Group a diff into hunks with `context` unchanged lines around changes. */
export function hunks(lines: DiffLine[], context = 3): Hunk[] {
  const changed = lines.map((l, i) => (l.kind === "same" ? -1 : i)).filter((i) => i >= 0);
  if (!changed.length) return [];
  const out: Hunk[] = [];
  let start = Math.max(0, changed[0] - context);
  let end = Math.min(lines.length, changed[0] + context + 1);
  const flush = () => {
    const slice = lines.slice(start, end);
    const firstOld = slice.find((l) => l.oldNo !== null)?.oldNo ?? null;
    const firstNew = slice.find((l) => l.newNo !== null)?.newNo ?? null;
    const oldLines = slice.filter((l) => l.kind !== "add").length;
    const newLines = slice.filter((l) => l.kind !== "del").length;
    // An empty side starts at the line before the hunk, as diff -u writes it.
    const before = lines.slice(0, start);
    const oldStart = firstOld ?? before.filter((l) => l.kind !== "add").length;
    const newStart = firstNew ?? before.filter((l) => l.kind !== "del").length;
    out.push({ oldStart, oldLines, newStart, newLines, lines: slice });
  };
  for (const index of changed.slice(1)) {
    if (index - context <= end) {
      end = Math.min(lines.length, index + context + 1);
    } else {
      flush();
      start = index - context;
      end = Math.min(lines.length, index + context + 1);
    }
  }
  flush();
  return out;
}

/** A unified diff of two texts, as `diff -u` writes it. */
export function unifiedDiff(oldText: string, newText: string, oldName = "original", newName = "suggested", context = 3): string {
  const groups = hunks(diffLines(oldText, newText), context);
  if (!groups.length) return "";
  const range = (startNo: number, count: number) => (count === 1 ? `${startNo}` : `${startNo},${count}`);
  const out = [`--- ${oldName}`, `+++ ${newName}`];
  for (const h of groups) {
    out.push(`@@ -${range(h.oldStart, h.oldLines)} +${range(h.newStart, h.newLines)} @@`);
    for (const l of h.lines) out.push((l.kind === "add" ? "+" : l.kind === "del" ? "-" : " ") + l.text);
  }
  return out.join("\n") + "\n";
}

export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const l of lines) {
    if (l.kind === "add") added++;
    else if (l.kind === "del") removed++;
  }
  return { added, removed };
}

/** Apply a diff's new side, which must give back the new text (for tests). */
export function newSide(lines: DiffLine[]): string[] {
  return lines.filter((l) => l.kind !== "del").map((l) => l.text);
}

export function oldSide(lines: DiffLine[]): string[] {
  return lines.filter((l) => l.kind !== "add").map((l) => l.text);
}
