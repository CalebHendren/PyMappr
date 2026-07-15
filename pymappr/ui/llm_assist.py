"""LLM Assist dialog (experimental, dev-only).

Reachable only through the "Enable experimental features (dev only)"
toggle at the bottom of the control panel - there are no other entry
points and no README mention. See pymappr/llm.py for what is (and is
deliberately not) sent to the provider.
"""

from __future__ import annotations

import io
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pymappr import codecheck, llm, projects

WRAP = 520
WARNING_BG = "#fff3cd"
WARNING_FG = "#664d03"
WARNING_TEXT = (
    "\N{WARNING SIGN} Use at your own risk. By default this sends your "
    "map settings and dataset column names only - never your data rows, "
    "coordinates, or category values - to the provider you choose, using "
    "your own API key. (You can opt in below to also send the first few "
    "rows of data.) LLMs make mistakes and invent details: always verify "
    "the generated code and run it yourself, comparing its output to your "
    "map. If you don't, you have not done your due diligence as a "
    "researcher.")
IMAGE_DPI = 150
CODE_EXTENSIONS = {"Python": ".py", "R": ".R"}
# Sentinel language: export in whatever language the user types below.
OTHER_LANGUAGE = "Other"
OTHER_LANGUAGE_NOTE = (
    "\N{WARNING SIGN} Only Python and R are tested. Any other language is "
    "best-effort - the generated code may be wrong or may not run at all.")


class LLMAssistDialog(tk.Toplevel):
    """Ask an LLM for a Python/R script that recreates the current map."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("LLM Assist (experimental)")
        self.transient(master)
        self.minsize(560, 620)
        self._worker: threading.Thread | None = None
        # The language the last reply was generated for, so validation
        # still checks the right syntax after the radio button changes.
        self._generated_language: str | None = None
        # Per-provider field edits, seeded from saved settings.
        stored = projects.load_settings().get("llm_assist", {})
        stored = stored if isinstance(stored, dict) else {}
        self._fields: dict[str, dict] = {
            name: dict(values) for name, values
            in dict(stored.get("providers", {})).items()}

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        warning = tk.Label(body, text=WARNING_TEXT, bg=WARNING_BG,
                           fg=WARNING_FG, wraplength=WRAP,
                           justify="left", padx=10, pady=8)
        warning.pack(fill="x")

        # ----------------------------------------------- provider row
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(10, 2))
        ttk.Label(row, text="Provider:").pack(side="left")
        provider = str(stored.get("provider", ""))
        self._provider_var = tk.StringVar(
            value=provider if provider in llm.PROVIDERS
            else next(iter(llm.PROVIDERS)))
        box = ttk.Combobox(row, textvariable=self._provider_var,
                           values=list(llm.PROVIDERS), state="readonly",
                           width=28)
        box.pack(side="left", padx=(6, 12))
        box.bind("<<ComboboxSelected>>", lambda _e: self._on_provider())
        ttk.Label(row, text="Model:").pack(side="left")
        self._model_var = tk.StringVar()
        # Editable combobox: the provider's known models seed the dropdown,
        # but a typed-in model (a newer release, a fine-tune) still works.
        self._model_box = ttk.Combobox(row, textvariable=self._model_var,
                                       width=22)
        self._model_box.pack(side="left", fill="x", expand=True, padx=(6, 0))

        row = ttk.Frame(body)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="API key:").pack(side="left")
        self._key_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._key_var).pack(
            side="left", fill="x", expand=True, padx=(6, 0))
        ttk.Label(body, text="(stored unencrypted in this app's local "
                             "settings; sent only to the provider)",
                  foreground="#666666").pack(anchor="w")
        # A clickable link to where the selected provider hands out API
        # keys; the text/target are refreshed in _load_provider_fields.
        self._key_link = tk.Label(body, text="", foreground="#0645ad",
                                  cursor="hand2",
                                  font=("TkDefaultFont", 9, "underline"))
        self._key_link.pack(anchor="w")
        self._key_link.bind("<Button-1>", lambda _e: self._open_key_url())

        row = ttk.Frame(body)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Endpoint URL:").pack(side="left")
        self._endpoint_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._endpoint_var).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        # ---------------------------------------------------- options
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 2))
        ttk.Label(row, text="Code language:").pack(side="left")
        self._language_var = tk.StringVar(
            value=stored.get("language")
            if stored.get("language") in (*llm.LANGUAGES, OTHER_LANGUAGE)
            else "Python")
        for language in llm.LANGUAGES:
            ttk.Radiobutton(row, text=language, value=language,
                            variable=self._language_var,
                            command=self._on_language).pack(
                side="left", padx=(8, 0))
        ttk.Radiobutton(row, text="Other (specify)", value=OTHER_LANGUAGE,
                        variable=self._language_var,
                        command=self._on_language).pack(side="left",
                                                        padx=(8, 0))
        self._other_language_var = tk.StringVar(
            value=str(stored.get("other_language", "")))
        self._other_language_entry = ttk.Entry(
            row, textvariable=self._other_language_var, width=14)
        self._other_language_entry.pack(side="left", fill="x", expand=True,
                                        padx=(6, 0))
        self._other_language_note = ttk.Label(
            body, text="", foreground=WARNING_FG, wraplength=WRAP,
            justify="left")
        self._other_language_note.pack(anchor="w")
        self._image_var = tk.BooleanVar(
            value=bool(stored.get("send_image", False)))
        ttk.Checkbutton(
            body, text="Also send a PNG image of the current map",
            variable=self._image_var).pack(anchor="w", pady=(4, 0))
        ttk.Label(body, text="(the image goes to the provider too; the "
                             "chosen model must support image input)",
                  foreground="#666666", wraplength=WRAP).pack(anchor="w")

        # Opt-in data sample: off by default. When on, the first N rows of
        # each dataset - real coordinates and category values - are sent
        # for slightly better accuracy.
        sample_row = ttk.Frame(body)
        sample_row.pack(fill="x", pady=(4, 0))
        self._sample_var = tk.BooleanVar(
            value=bool(stored.get("send_sample", False)))
        ttk.Checkbutton(sample_row, text="Also send the first",
                        variable=self._sample_var,
                        command=self._on_sample_toggle).pack(side="left")
        self._sample_count_var = tk.StringVar(
            value=str(stored.get("sample_rows", 5)))
        self._sample_spin = ttk.Spinbox(
            sample_row, from_=1, to=100, increment=1, width=5,
            textvariable=self._sample_count_var, command=self._save_settings)
        self._sample_spin.pack(side="left", padx=(4, 4))
        self._sample_spin.bind("<KeyRelease>",
                               lambda _e: self._save_settings())
        ttk.Label(sample_row, text="row(s) of each dataset").pack(
            side="left")
        ttk.Label(body, text="(shares real data values - coordinates and "
                             "category values - for those rows; off shares "
                             "only column names)",
                  foreground="#666666", wraplength=WRAP).pack(anchor="w")
        if not self._sample_var.get():
            self._sample_spin.config(state="disabled")

        ttk.Label(body, text="Add to the prompt (what the columns mean, "
                             "what to look out for, ...):").pack(
            anchor="w", pady=(6, 0))
        self._extra = tk.Text(body, height=3, width=64, undo=True)
        self._extra.pack(fill="x")
        self._extra.insert("1.0", str(stored.get("extra", "")))

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Preview what will be sent"
                             "\N{HORIZONTAL ELLIPSIS}",
                   command=self._preview).pack(side="left")
        self._generate_button = ttk.Button(
            row, text="Generate code", command=self._on_generate)
        self._generate_button.pack(side="right")
        self._status = ttk.Label(body, text="", foreground="#666666",
                                 wraplength=WRAP)
        self._status.pack(anchor="w", pady=(4, 2))

        # ----------------------------------------------------- output
        out_frame = ttk.Frame(body)
        out_frame.pack(fill="both", expand=True)
        self._output = tk.Text(out_frame, height=14, width=64,
                               state="disabled", wrap="none")
        yscroll = ttk.Scrollbar(out_frame, orient="vertical",
                                command=self._output.yview)
        xscroll = ttk.Scrollbar(out_frame, orient="horizontal",
                                command=self._output.xview)
        self._output.configure(yscrollcommand=yscroll.set,
                               xscrollcommand=xscroll.set)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self._output.pack(side="left", fill="both", expand=True)

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Copy reply",
                   command=self._copy).pack(side="left")
        ttk.Button(row, text="Save code as\N{HORIZONTAL ELLIPSIS}",
                   command=self._save).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Validate code",
                   command=self._validate).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Close",
                   command=self._close).pack(side="right")

        self._current_provider = self._provider_var.get()
        self._load_provider_fields()
        self._on_language()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())

    # ------------------------------------------------------- settings

    def _load_provider_fields(self) -> None:
        name = self._provider_var.get()
        provider = llm.PROVIDERS[name]
        stored = self._fields.get(name, {})
        self._model_box.configure(values=list(provider.models))
        self._model_var.set(str(stored.get("model") or provider.model))
        self._key_var.set(str(stored.get("api_key", "")))
        self._endpoint_var.set(str(stored.get("endpoint")
                                   or provider.endpoint))
        if provider.key_url:
            self._key_link.config(
                text=f"Get an API key for {name} \N{NORTH EAST ARROW}")
        else:
            self._key_link.config(text="")

    def _open_key_url(self) -> None:
        """Open the selected provider's API-key page in a web browser."""
        import webbrowser

        url = llm.PROVIDERS[self._provider_var.get()].key_url
        if url:
            webbrowser.open(url)

    def _remember_provider_fields(self) -> None:
        self._fields[self._current_provider] = {
            "model": self._model_var.get().strip(),
            "api_key": self._key_var.get().strip(),
            "endpoint": self._endpoint_var.get().strip(),
        }

    def _on_provider(self) -> None:
        # The combobox already holds the new provider; keep the edits
        # made while the previous one was selected.
        self._remember_provider_fields()
        self._current_provider = self._provider_var.get()
        self._load_provider_fields()
        self._save_settings()

    def _on_language(self) -> None:
        # Enable the free-text language box only for "Other", and show the
        # untested-language warning while it's in play.
        other = self._language_var.get() == OTHER_LANGUAGE
        self._other_language_entry.config(
            state="normal" if other else "disabled")
        self._other_language_note.config(
            text=OTHER_LANGUAGE_NOTE if other else "")
        self._save_settings()

    def _on_sample_toggle(self) -> None:
        # The row-count spinbox is only meaningful while the box is ticked.
        self._sample_spin.config(
            state="normal" if self._sample_var.get() else "disabled")
        self._save_settings()

    def _sample_count(self) -> int:
        """The configured sample size, clamped to a sane range."""
        try:
            return max(1, min(int(float(self._sample_count_var.get())), 1000))
        except (TypeError, ValueError):
            return 5

    def _effective_sample(self) -> int:
        """Rows to actually send: the configured count, or 0 when off."""
        return self._sample_count() if self._sample_var.get() else 0

    def _effective_language(self) -> str:
        """The language actually requested: the typed-in name for "Other",
        otherwise the selected radio value."""
        if self._language_var.get() == OTHER_LANGUAGE:
            return self._other_language_var.get().strip()
        return self._language_var.get()

    def _save_settings(self) -> None:
        settings = projects.load_settings()
        settings["llm_assist"] = {
            "provider": self._provider_var.get(),
            "language": self._language_var.get(),
            "other_language": self._other_language_var.get().strip(),
            "send_image": self._image_var.get(),
            "send_sample": self._sample_var.get(),
            "sample_rows": self._sample_count(),
            "extra": self._extra.get("1.0", "end").strip(),
            "providers": self._fields,
        }
        projects.save_settings(settings)

    # --------------------------------------------------------- prompt

    def _build_prompt(self) -> tuple[str, str]:
        sample = self._effective_sample()
        summary = llm.describe_map(self.app._collect_state(),
                                   self.app.entries, sample=sample)
        return llm.build_prompt(summary, self._effective_language(),
                                extra=self._extra.get("1.0", "end"),
                                with_image=self._image_var.get(),
                                with_sample=sample > 0)

    def _preview(self) -> None:
        system, user = self._build_prompt()
        window = tk.Toplevel(self)
        window.title("Exact prompt to be sent")
        window.transient(self)
        frame = ttk.Frame(window, padding=8)
        frame.pack(fill="both", expand=True)
        note = ("The image of the map is attached as well (not shown "
                "here).\n\n" if self._image_var.get() else "")
        text = tk.Text(frame, width=88, height=32, wrap="word")
        scroll = ttk.Scrollbar(frame, orient="vertical",
                               command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", f"{note}=== System prompt ===\n{system}\n\n"
                           f"=== User message ===\n{user}\n")
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Button(window, text="Close",
                   command=window.destroy).pack(pady=(0, 8))

    # ------------------------------------------------------- generate

    def _render_map_png(self) -> bytes:
        buffer = io.BytesIO()
        self.app.renderer.fig.savefig(buffer, format="png",
                                      dpi=IMAGE_DPI, facecolor="white")
        return buffer.getvalue()

    def _on_generate(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._remember_provider_fields()
        self._save_settings()
        name = self._provider_var.get()
        provider = llm.PROVIDERS[name]
        model = self._model_var.get().strip()
        api_key = self._key_var.get().strip()
        endpoint = self._endpoint_var.get().strip()
        if not endpoint or not model:
            self._status.config(
                text="Fill in the model and endpoint URL first.")
            return
        if not api_key and name != "Custom (OpenAI-compatible)":
            self._status.config(
                text="Enter your API key first"
                     + (f" ({provider.key_hint})" if provider.key_hint
                        else "") + ".")
            return
        if not self._effective_language():
            self._status.config(
                text="Type the language to export to first.")
            return
        try:
            system, user = self._build_prompt()
            # Matplotlib isn't thread-safe: render on the UI thread.
            image = (self._render_map_png() if self._image_var.get()
                     else None)
        except Exception as exc:  # noqa: BLE001 - show any build error
            self._status.config(text=f"Could not prepare the request: "
                                     f"{exc}")
            return

        self._generate_button.config(state="disabled")
        self._generated_language = self._effective_language()
        self._status.config(
            text=f"Asking {model} via {name}\N{HORIZONTAL ELLIPSIS} "
                 "(this can take a few minutes)")

        def worker() -> None:
            try:
                reply = llm.generate_code(provider.api, endpoint, model,
                                          api_key, system, user,
                                          image_png=image)
            except llm.LLMError as exc:
                self._deliver(error=str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - never kill the app
                self._deliver(error=f"Unexpected error: {exc}")
                return
            self._deliver(reply=reply)

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _deliver(self, reply: str | None = None,
                 error: str | None = None) -> None:
        """Marshal the worker result back onto the UI thread."""
        def apply() -> None:
            self._generate_button.config(state="normal")
            if error is not None:
                self._status.config(text=f"Failed: {error}")
                return
            self._status.config(
                text="Done. Verify this code and run it yourself - do "
                     "not trust it blindly.")
            self._output.configure(state="normal")
            self._output.delete("1.0", "end")
            self._output.insert("1.0", reply or "")
            self._output.configure(state="disabled")

        try:
            self.after(0, apply)
        except (tk.TclError, RuntimeError):
            pass  # dialog closed / app shutting down while generating

    # --------------------------------------------------------- output

    def _reply_text(self) -> str:
        return self._output.get("1.0", "end").strip()

    def _copy(self) -> None:
        reply = self._reply_text()
        if not reply:
            self._status.config(text="Nothing to copy yet.")
            return
        self.clipboard_clear()
        self.clipboard_append(reply)
        self._status.config(text="Reply copied to the clipboard.")

    def _validate(self) -> None:
        """Static check of the reply's code block: syntax (real parse for
        Python, bracket/string scan for R) plus leftover placeholders.
        Offline and LLM-free; passing still doesn't mean correct."""
        reply = self._reply_text()
        if not reply:
            self._status.config(text="Nothing to validate yet.")
            return
        language = self._generated_language or self._effective_language()
        if language not in codecheck.LANGUAGES:
            self._status.config(
                text=f"No offline validator for {language or 'this language'}"
                     " - only Python and R can be checked. Read and run the "
                     "code yourself.")
            return
        code = llm.extract_code(reply)
        issues = codecheck.validate_code(language, code)
        summary = codecheck.summarize(language, issues)
        if not issues:
            self._status.config(text=summary)
            return
        errors = codecheck.has_errors(issues)
        self._status.config(
            text=f"Validation found {len(issues)} issue"
                 f"{'s' if len(issues) != 1 else ''} - "
                 "see the details window.")
        show = messagebox.showwarning if errors else messagebox.showinfo
        show("Validate code",
             summary + "\n\nLLMs often need a second attempt: fix the "
             "code yourself or regenerate.", parent=self)

    def _save(self) -> None:
        reply = self._reply_text()
        if not reply:
            self._status.config(text="Nothing to save yet.")
            return
        language = self._generated_language or self._effective_language()
        extension = CODE_EXTENSIONS.get(language, ".txt")
        path = filedialog.asksaveasfilename(
            parent=self, title="Save generated code",
            defaultextension=extension,
            initialfile="recreate_map" + extension,
            filetypes=[(f"{language or 'Code'} script", "*" + extension),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(llm.extract_code(reply) + "\n")
        except OSError as exc:
            self._status.config(text=f"Could not save: {exc}")
            return
        self._status.config(text=f"Saved to {path}. Run it yourself and "
                                 "compare the output to your map.")

    def _close(self) -> None:
        self._remember_provider_fields()
        self._save_settings()
        self.destroy()
