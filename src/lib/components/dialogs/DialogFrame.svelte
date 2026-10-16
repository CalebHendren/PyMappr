<script lang="ts">
  // A modal dialog frame for the document dialogs (same look as Modal.svelte,
  // kept here so these dialogs stand alone).
  import type { Snippet } from "svelte";
  import { X } from "@lucide/svelte";

  let {
    title,
    onClose,
    children,
    actions,
    width = "w-[min(560px,92vw)]",
  }: { title: string; onClose: () => void; children: Snippet; actions?: Snippet; width?: string } = $props();

  let dialog: HTMLDialogElement;
  $effect(() => {
    dialog.showModal();
  });
</script>

<dialog
  bind:this={dialog}
  class="m-auto max-h-[85vh] {width} overflow-hidden rounded-lg border border-line bg-panel p-0 text-ink shadow-xl backdrop:bg-black/35"
  oncancel={(e) => {
    e.preventDefault();
    onClose();
  }}
>
  <div class="flex max-h-[85vh] flex-col">
    <header class="flex items-center border-b border-line px-5 py-3">
      <h2 class="flex-1 truncate text-[15px] font-semibold">{title}</h2>
      <button class="btn !p-1" onclick={onClose} aria-label="Close"><X size={16} /></button>
    </header>
    <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
      {@render children()}
    </div>
    {#if actions}
      <footer class="flex items-center gap-2 border-t border-line px-5 py-3">
        {@render actions()}
      </footer>
    {/if}
  </div>
</dialog>
