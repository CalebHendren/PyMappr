<script lang="ts" module>
  export type MenuItem =
    | { label: string; shortcut?: string; action: () => void; disabled?: boolean; checked?: boolean }
    | { separator: true };
  export type Menu = { label: string; items: MenuItem[] };
</script>

<script lang="ts">
  // PyMappr's File / View / Help menus as an in-window menu bar.
  let { menus }: { menus: Menu[] } = $props();

  let open = $state<number | null>(null);

  function run(item: MenuItem) {
    open = null;
    if ("action" in item && !item.disabled) item.action();
  }
</script>

<svelte:window
  onclick={(e) => {
    if (!(e.target as Element).closest("[data-menubar]")) open = null;
  }}
  onkeydown={(e) => {
    if (e.key === "Escape") open = null;
  }}
/>

<nav data-menubar class="flex h-8 items-center gap-0.5 border-b border-line bg-panel px-1.5 text-[13px]">
  {#each menus as menu, i (menu.label)}
    <div class="relative">
      <button
        class="rounded px-2.5 py-1 hover:bg-accent-soft"
        class:bg-accent-soft={open === i}
        aria-haspopup="menu"
        aria-expanded={open === i}
        onclick={() => (open = open === i ? null : i)}
        onmouseenter={() => {
          if (open !== null) open = i;
        }}>{menu.label}</button
      >
      {#if open === i}
        <div role="menu" class="absolute left-0 top-full z-50 mt-0.5 min-w-60 rounded-md border border-line bg-raised py-1 shadow-lg">
          {#each menu.items as item, j (j)}
            {#if "separator" in item}
              <div class="my-1 h-px bg-line"></div>
            {:else}
              <button
                role="menuitem"
                class="flex w-full items-center gap-3 px-3 py-1.5 text-left hover:bg-accent-soft disabled:opacity-40 disabled:hover:bg-transparent"
                disabled={item.disabled}
                onclick={() => run(item)}
              >
                <span class="w-3 text-accent">{item.checked ? "✓" : ""}</span>
                <span class="flex-1">{item.label}</span>
                {#if item.shortcut}<span class="text-[12px] text-muted">{item.shortcut}</span>{/if}
              </button>
            {/if}
          {/each}
        </div>
      {/if}
    </div>
  {/each}
</nav>
