"""The plain widgets every tab is built from: scrollable tabs,
sections, and labelled rows of combo boxes, spinboxes, entries and
colour swatches."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from pymappr.ui.control_panel.tables import PANEL_WIDTH, TYPING_PAUSE_MS


class WidgetsMixin:
    """Widget builders shared by every tab."""

    def _scroll_tab(self, title: str) -> ttk.Frame:
        """Add a notebook tab wrapping a vertically scrollable frame."""
        outer = ttk.Frame(self.notebook)
        self.notebook.add(outer, text=title)
        bg = ttk.Style().lookup("TFrame", "background") or "white"
        canvas = tk.Canvas(outer, width=PANEL_WIDTH, highlightthickness=0,
                           background=bg)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw",
                             width=PANEL_WIDTH - 18)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._bind_mousewheel(canvas)
        return inner

    def _section(self, parent, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=(8, 4))
        frame.pack(fill="x", padx=6, pady=4)
        return frame

    def _combo_row(self, parent, label: str, var: tk.StringVar,
                   values, command, width: int = 14) -> ttk.Combobox:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        box = ttk.Combobox(row, textvariable=var, state="readonly",
                           values=list(values), width=width)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: command())
        return box

    def _check(self, parent, text: str, var: tk.BooleanVar, command) -> None:
        ttk.Checkbutton(parent, text=text, variable=var,
                        command=command).pack(anchor="w")

    def _collapsible(self, parent, title: str, expanded: bool = False):
        """A section that folds away, so a tab can carry many settings
        without becoming an endless scroll. ttk has no expander widget, so
        this is a header button that packs and forgets the body frame.

        Returns the body frame to put controls in.
        """
        outer = ttk.Frame(parent)
        outer.pack(fill="x", padx=6, pady=(4, 0))
        header = ttk.Button(outer, style="Toolbutton")
        header.pack(fill="x")
        body = ttk.LabelFrame(outer, padding=(8, 4))
        state = {"open": bool(expanded)}

        def render() -> None:
            arrow = ("\N{BLACK DOWN-POINTING SMALL TRIANGLE}" if state["open"]
                     else "\N{BLACK RIGHT-POINTING SMALL TRIANGLE}")
            header.config(text=f"{arrow}  {title}")
            if state["open"]:
                body.pack(fill="x", pady=(2, 0))
            else:
                body.pack_forget()

        def toggle() -> None:
            state["open"] = not state["open"]
            render()

        header.config(command=toggle)
        render()
        return body

    def _after_typing(self, command, delay_ms: int = TYPING_PAUSE_MS):
        """A key handler that calls *command* once typing pauses, rather
        than on every keystroke - each call redraws the map."""
        pending: list[str] = []

        def schedule(_event=None) -> None:
            if pending:
                self.after_cancel(pending.pop())
            pending.append(self.after(
                delay_ms, lambda: (pending.clear(), command())))

        return schedule

    def _spin_row(self, parent, label: str, var: tk.StringVar, from_, to,
                  increment, command, width: int = 6):
        """A labelled spinbox that reports at once on an arrow click and
        once typing pauses."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        spin = ttk.Spinbox(row, from_=from_, to=to, increment=increment,
                           width=width, textvariable=var, command=command)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", self._after_typing(command))
        return spin

    def _entry_row(self, parent, label: str, var: tk.StringVar, command,
                   width: int = 14):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        entry = ttk.Entry(row, textvariable=var, width=width)
        entry.pack(side="right")
        entry.bind("<KeyRelease>", self._after_typing(command))
        return entry

    def _color_row(self, parent, label: str, var: tk.StringVar, command):
        """A labelled colour swatch button opening the system colour picker.

        The chosen colour lives in *var* as a hex string, so it saves and
        restores with everything else.
        """
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        button = tk.Button(row, width=4, relief="ridge",
                           bg=var.get() or "#ffffff",
                           activebackground=var.get() or "#ffffff")
        button.pack(side="right")

        def pick() -> None:
            _rgb, chosen = colorchooser.askcolor(
                color=var.get() or "#ffffff", parent=self, title=label)
            if chosen:
                var.set(chosen)
                button.config(bg=chosen, activebackground=chosen)
                command()

        button.config(command=pick)
        self._color_buttons[str(var)] = button
        return button

    def _named_combo(self, parent, label: str, var: tk.StringVar,
                     names: dict, command, width: int = 16):
        """A combo box over a display-name -> stored-value mapping."""
        return self._combo_row(parent, label, var, list(names), command,
                               width=width)

    def _bind_mousewheel(self, canvas: tk.Canvas) -> None:
        def on_wheel(event):
            delta = -1 if (event.num == 4 or event.delta > 0) else 1
            canvas.yview_scroll(delta, "units")

        def bind_all(_e):
            canvas.bind_all("<MouseWheel>", on_wheel)
            canvas.bind_all("<Button-4>", on_wheel)
            canvas.bind_all("<Button-5>", on_wheel)

        def unbind_all(_e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_all)
        canvas.bind("<Leave>", unbind_all)
