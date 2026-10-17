import { beforeEach, describe, expect, it, vi } from "vitest";

const saved: Record<string, unknown>[] = [];
let settings: Record<string, unknown> = {};

vi.mock("./api", () => ({
  api: {
    appInfo: async () => ({}),
    settings: async () => settings,
    setSettings: async (patch: Record<string, unknown>) => {
      saved.push(patch);
      return patch;
    },
  },
}));

import { store } from "./store.svelte";

describe("Ko-fi button preference", () => {
  beforeEach(() => {
    saved.length = 0;
    settings = { theme: "light" };
    vi.stubGlobal("document", { documentElement: { dataset: {} } });
  });

  it("shows the button until it is dismissed", async () => {
    await store.init();
    expect(store.kofiHidden).toBe(false);
  });

  it("restores a dismissed button from the saved settings", async () => {
    settings = { theme: "light", kofiHidden: true };
    await store.init();
    expect(store.kofiHidden).toBe(true);
  });

  it("only a saved true hides it", async () => {
    settings = { theme: "light", kofiHidden: "yes" };
    await store.init();
    expect(store.kofiHidden).toBe(false);
  });

  it("saves the choice when dismissed", () => {
    store.setKofiHidden(true);
    expect(store.kofiHidden).toBe(true);
    expect(saved).toEqual([{ kofiHidden: true }]);
  });
});
