<script lang="ts">
  // Ask for a name (Save project as).
  import Modal from "./Modal.svelte";

  let { title, initial = "", onDone }: { title: string; initial?: string; onDone: (name: string | null) => void } = $props();

  // svelte-ignore state_referenced_locally
  let name = $state(initial);
  const ok = $derived(name.trim().length > 0);
</script>

<Modal {title} onClose={() => onDone(null)}>
  <form
    class="w-96 max-w-full"
    onsubmit={(e) => {
      e.preventDefault();
      if (ok) onDone(name.trim());
    }}
  >
    <label class="block">
      <span class="label">Project name</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input class="field mt-1" bind:value={name} autofocus />
    </label>
  </form>
  {#snippet actions()}
    <button class="btn" onclick={() => onDone(null)}>Cancel</button>
    <button class="btn-primary" disabled={!ok} onclick={() => onDone(name.trim())}>Save</button>
  {/snippet}
</Modal>
