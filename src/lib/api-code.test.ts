import { describe, expect, it } from "vitest";
import { withRevisionHeader } from "./api-code";

describe("withRevisionHeader", () => {
  const day = new Date(2026, 9, 11);
  it("goes after a Python shebang", () => {
    expect(withRevisionHeader("#!/usr/bin/env python3\nprint(1)\n", "anthropic/claude-sonnet-5.5", day)).toBe(
      "#!/usr/bin/env python3\n# Revised with AI assistance (anthropic/claude-sonnet-5.5, 2026-10-11). Review before relying on it.\nprint(1)\n",
    );
  });
  it("goes first in an R script", () => {
    expect(withRevisionHeader("# Made with\nx <- 1\n", "m\nx", day)).toBe(
      "# Revised with AI assistance (m x, 2026-10-11). Review before relying on it.\n# Made with\nx <- 1\n",
    );
  });
});
