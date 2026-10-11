<script lang="ts">
  import type { Snippet } from "svelte";
  let { title, children }: { title: string; children: Snippet } = $props();
</script>

<section class="mb-5">
  <h3 class="mb-2 text-[13px] font-semibold text-ink">{title}</h3>
  <div class="space-y-2.5">
    {@render children()}
  </div>
</section>
