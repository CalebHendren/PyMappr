# RustyMappr — working agreement for Claude

RustyMappr is a Rust + Tauri 2 + Svelte 5 + Tailwind v4 + TypeScript port of PyMappr
(`C:\PyCharm\PyMappr`). It turns species locality tables into publication distribution maps.

## Git: local repo, no remote

- **Never commit straight to `main`.** Work on a branch (`feature/…`, `fix/…`, or a
  version-named branch). Do not mention Claude or Anthropic in branch names. The owner merges.
- There is no `main` yet: work so far is on `feature/proof-of-concept`, then `feature/full-port`.
  Branch from the owner's current base branch; creating `main` is the owner's call.
- **Never push anywhere.** There is no remote. Do not add one; creating a remote is the owner's call.
- Parallel work lives in git worktrees under `C:\PyCharm\RustyMappr-ws\` (`ws/rendering`,
  `ws/symbology`, `ws/codegen`). Do not rewrite or delete another workstream's branch.
- Never rewrite history on a branch the owner may have merged or based work on.

## No Claude / Anthropic attribution — ever

- Commits, commit trailers, branch names and merge messages must read as authored solely by the owner.
- Never add `Generated with Claude Code` (or any variant), `Co-Authored-By: Claude …`, any
  `…@anthropic.com` address, or any mention of Claude, Claude Code, Anthropic or "AI-generated" in
  commit messages.
- Write commit messages plainly, as if the owner wrote them.
- The product's own AI code-check feature may name its providers in code and UI text. That is fine.

## Versioning — `MAJOR.MINOR.PATCH`

The version lives in three places that must always match:

1. root `Cargo.toml`, `[workspace.package] version`
2. `package.json`, `version`
3. `src-tauri/tauri.conf.json`, `version`

Bump the part that matches the change, and state the bump in the commit or merge message:

- **`x.0.0`** — breaking changes (for example a change that makes `.pymappr` files unreadable).
- **`0.x.0`** — new features or rewrites.
- **`0.0.x`** — small bug fixes.

The scheme is a guide. If the owner names a number, use it.

## Subagents — 3 at once, each with at most 1 of its own (6 total)

- You may dispatch subagents without asking first, at most 3 running at the same time. Each can
  be Opus, Sonnet or Haiku.
- Each of those may dispatch at most 1 subagent of its own. That one must be a lesser model
  (Sonnet or Haiku, never Opus, never bigger than its parent) and may not dispatch any. Nothing
  deeper than main session, subagent, sub-subagent; 6 agents at most.
- Say so in every brief. First level: "you may dispatch one Sonnet or Haiku subagent". Second
  level: "you may not dispatch any".
- Pick the cheapest model that fits: Haiku for git housekeeping and status checks, Sonnet for
  simple or mechanical work and routine reviews, Opus for design, subtle logic and whole-branch
  reviews.
- Only the main session or Opus subagents fix app logic bugs. Sonnet and Haiku subagents report them.

## Compatibility with PyMappr is a requirement

- `.pymappr` projects and `.pymappr-preset` files must stay readable and writable by both apps.
  Never change their shape without checking PyMappr's loader.
- `src/lib/model.ts` mirrors PyMappr's `state.py` exactly. Its defaults come from
  `src/lib/pymappr-defaults.json`, which is generated from PyMappr. Do not hand-edit that file.
- `src/lib/styles.ts` copies PyMappr's palette and layer-style tables, with one deliberate
  exception: land fill is white, by the owner's choice.
- When behaviour is unclear, PyMappr's code is the reference. Read it before guessing.
- Regenerate reference data with `scripts/pymappr_reference.py`, run with
  `C:\PyCharm\PyMappr\.venv\Scripts\python.exe`.
- Fixtures in `src/lib/fixtures/` are real PyMappr output; keep them in sync when the format moves.

## Owner decisions to preserve

- The base map is white.
- No insect icon. The app icon is PyMappr's globe and pin.
- A visible light/dark switch.
- The Ko-fi link (https://ko-fi.com/calebhendren) stays in the Help menu and the panel footer.
- The "Show advanced options" checkbox hides only the political extras: sovereignty, map units,
  subunits, dependencies, disputed areas and lines, the time zones layer and labels, maritime,
  and EEZ. It hides nothing else.
- Districts outside the US come from geoBoundaries.
- The AI code check is bring-your-own OpenRouter key. The user chooses what is sent (code only by
  default), and a disclaimer is shown.

## Architecture map

| Path | Role |
|---|---|
| `crates/mappr-core/` | Everything with no Tauri dependency: coords, table, projection, basemap, render, export |
| `src-tauri/src/core.rs` | `Core::dispatch`. One `cmd_*.rs` module per area (`app`, `map`, `docs`, `code`); `jobs.rs` and `downloader.rs` are support. All UI calls go through the single Tauri `core` command |
| `src-tauri/src/lib.rs` | Tauri setup and the `core` command |
| `src-tauri/src/bin/devbridge.rs` | Dev HTTP bridge on `127.0.0.1:1430` (feature `devbridge`); POST `/core` with `{"cmd", "args"}` |
| `src/lib/api.ts` | Transport plus the map rendering contract types |
| `src/lib/model.ts` | Project state, mirroring PyMappr's `state.py` |
| `src/lib/store.svelte.ts` | App store (runes) |
| `src/lib/layout.ts` | Figure geometry in pt; export scale follows PyMappr's `export_geometry` |
| `src/lib/components/map/` | `MapView`, `MapSvg`, `Scene`. `Scene` is also mounted offscreen for exports so screen and export match |

Add a new backend command to the matching `cmd_*` module. Do not add a second Tauri command.

## Run, test, verify

- Node is at `C:\Program Files\nodejs`. A shell opened before it was installed may need it on PATH.
  In PowerShell use `npm.cmd`.
- Setup and run: `npm install`, then `npm run tauri dev`.
- Rust: `cargo test --workspace` and `cargo clippy --workspace --all-targets`.
- Frontend: `npm run check` (svelte-check) and `npm test` (vitest).
- Release build: `npm run tauri build -- --no-bundle` (about 5 minutes with LTO).
- Tests that need PyMappr's data read `PYMAPPR_DIR` (default `C:\PyCharm\PyMappr`) and skip when
  it is missing. A skipped test is not a pass; say so when reporting.
- **Verifying the UI:** the owner declined screen control of the native window. Run
  `npm run bridge` and `npm run dev`, then drive `http://127.0.0.1:1420` in the browser pane.
  Ask the owner to do the final pass in the native window.
- Stroke widths in SVG are in map units, not `vector-effect`, because resvg ignores non-scaling
  strokes. Check exports, not only the screen.

## Worktrees

- Parallel work uses git worktrees outside the repo, in `C:\PyCharm\RustyMappr-ws\`. Each has
  `node_modules` as a junction to the main checkout's.
- Before removing a worktree, delete the junction itself, not its target. Deleting through the
  junction wipes the main checkout's `node_modules`.
- Branch worktrees from the current base branch, and re-check the version bump against it before
  merging back.

## Wiki

After a change a future session should know about, update
`C:\PyCharm\Claude\projects\RustyMappr.md` and append to `C:\PyCharm\Claude\log.md`
(per `C:\PyCharm\CLAUDE.md`). Use the `project-wiki` skill before starting work. This file wins
over the wiki where they disagree; the wiki page is partly out of date.

## Code style

- Match the surrounding code and its comment density: short comments that explain why, not what.
- Rust edition 2024. Let-chains are used, so Rust 1.88+ is required.
- Svelte 5 runes only (`$state`, `$derived`, `$props`). Runes work only in `.svelte` and
  `.svelte.ts` files; plain `.ts` files cannot use them.
- Tailwind v4 utilities; no separate CSS files for components unless the file already has one.
- No emojis in code, UI text or commit messages. Sentence case for headings and labels.
