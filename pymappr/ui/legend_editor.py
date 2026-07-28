"""Per-row legend editor: rename, hide, reorder, and restyle each row.

The rows are whatever the legend is currently made of - groups in group-by
mode, or color values, symbol values and nested pairs in the two-attribute
modes. Editing works the same way in all of them, which it did not used to:
the dialog simply refused to open whenever Symbol by was set.

Changes apply to the map immediately via the *on_change* callback.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from pymappr.styles import MARKERS, PointStyle

# Blank means "leave it as the styling rules worked it out", so a row that
# was only renamed still follows a palette change.
_UNSET = ""


class LegendEditorDialog(tk.Toplevel):
    """*rows* is ``[(key, value, default PointStyle, depth), ...]`` and
    *overrides* is the dataset's ``legend_overrides`` dict, edited in
    place."""

    def __init__(self, master, rows: list, overrides: dict, on_change,
                 on_reorder=None):
        super().__init__(master)
        self.title("Legend rows")
        self.transient(master)
        self.rows = list(rows)
        self.overrides = overrides
        self.on_change = on_change
        # Moving a row is meaningless unless the legend is set to order
        # manually, so the app switches it over rather than leaving the
        # button looking broken.
        self.on_reorder = on_reorder or on_change
        self._widgets: dict[str, dict] = {}

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Untick a row to leave it out of the legend; its points "
                 "stay on the map. A blank label uses the value from the "
                 "data.",
            wraplength=560, foreground="#666666").pack(anchor="w",
                                                       pady=(0, 8))

        header = ttk.Frame(outer)
        header.pack(fill="x")
        for column, text, width in ((0, "", 3), (1, "Row", 22),
                                    (2, "Label", 18), (3, "Color", 6),
                                    (4, "Symbol", 11), (5, "Size", 6),
                                    (6, "Move", 6)):
            ttk.Label(header, text=text, width=width,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=0, column=column, sticky="w", padx=4)

        # Scrollable list of rows.
        background = ttk.Style().lookup("TFrame", "background") or "white"
        canvas = tk.Canvas(outer, height=min(34 * max(len(self.rows), 1), 420),
                           highlightthickness=0, background=background)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for index, (key, value, style, depth) in enumerate(self.rows):
            self._build_row(body, index, key, value, style, depth)

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Reset all rows",
                   command=self._reset_all).pack(side="left")
        ttk.Button(buttons, text="Close",
                   command=self.destroy).pack(side="right")
        self.grab_set()

    # ----------------------------------------------------------- one row

    def _build_row(self, parent, index: int, key: str, value: str,
                   style: PointStyle, depth: int) -> None:
        override = self.overrides.get(key, {})

        shown = tk.BooleanVar(value=not override.get("hidden", False))
        ttk.Checkbutton(parent, variable=shown,
                        command=lambda k=key, v=shown: self._set(
                            k, "hidden", not v.get())).grid(
            row=index, column=0, padx=4, pady=3)

        # Nested children sit under their parent, as they do in the legend.
        ttk.Label(parent, text=("      " * depth) + (value or "(blank)"),
                  width=22).grid(row=index, column=1, sticky="w", padx=4)

        label = tk.StringVar(value=override.get("label") or _UNSET)
        entry = ttk.Entry(parent, textvariable=label, width=18)
        entry.grid(row=index, column=2, padx=4, pady=3)
        entry.bind("<KeyRelease>",
                   lambda _e, k=key, v=label: self._set(k, "label",
                                                        v.get().strip()))

        color_button = tk.Button(
            parent, width=4, relief="ridge",
            bg=override.get("color") or style.color,
            activebackground=override.get("color") or style.color,
            command=lambda k=key: self._pick_color(k))
        color_button.grid(row=index, column=3, padx=4, pady=3)

        marker = tk.StringVar(value=override.get("marker") or style.marker)
        marker_box = ttk.Combobox(parent, textvariable=marker,
                                  values=list(MARKERS), state="readonly",
                                  width=10)
        marker_box.grid(row=index, column=4, padx=4, pady=3)
        marker_box.bind("<<ComboboxSelected>>",
                        lambda _e, k=key, v=marker: self._set(k, "marker",
                                                              v.get()))

        size = tk.StringVar(value=f"{override.get('size') or style.size:g}")
        spin = ttk.Spinbox(parent, from_=4, to=400, increment=4, width=6,
                           textvariable=size,
                           command=lambda k=key, v=size: self._set_size(k,
                                                                        v))
        spin.grid(row=index, column=5, padx=4, pady=3)
        spin.bind("<KeyRelease>",
                  lambda _e, k=key, v=size: self._set_size(k, v))

        move = ttk.Frame(parent)
        move.grid(row=index, column=6, padx=4)
        ttk.Button(move, text="\N{UPWARDS ARROW}", width=2,
                   command=lambda i=index: self._move(i, -1)).pack(side="left")
        ttk.Button(move, text="\N{DOWNWARDS ARROW}", width=2,
                   command=lambda i=index: self._move(i, 1)).pack(side="left")

        self._widgets[key] = {"color": color_button, "label": label,
                              "marker": marker, "size": size, "shown": shown}

    # ------------------------------------------------------------ edits

    def _set(self, key: str, field: str, value) -> None:
        """Record one field of a row's customization, dropping it entirely
        when it goes back to the default so the project stays clean."""
        override = self.overrides.setdefault(key, {})
        if value in (None, "", False):
            override.pop(field, None)
        else:
            override[field] = value
        if not override:
            self.overrides.pop(key, None)
        self.on_change()

    def _set_size(self, key: str, var: tk.StringVar) -> None:
        try:
            size = float(var.get())
        except ValueError:
            return  # mid-edit; the spinbox reports on every keystroke
        if 1 <= size <= 1000:
            self._set(key, "size", size)

    def _pick_color(self, key: str) -> None:
        button = self._widgets[key]["color"]
        _rgb, chosen = colorchooser.askcolor(color=button.cget("bg"),
                                             parent=self,
                                             title="Color for this row")
        if chosen:
            button.config(bg=chosen, activebackground=chosen)
            self._set(key, "color", chosen)

    def _move(self, index: int, step: int) -> None:
        """Move a row up or down.

        Reordering writes an explicit position for *every* row, not just the
        two that swapped: a partial ordering would leave untouched rows to
        fall to the end, which is not what dragging one row up should do.
        """
        target = index + step
        if not 0 <= target < len(self.rows):
            return
        # A nested child may only move within its own parent's block, and a
        # parent moves as a block; swapping across the boundary would put a
        # species under the wrong genus.
        if self.rows[index][3] != self.rows[target][3]:
            return
        self.rows[index], self.rows[target] = (self.rows[target],
                                               self.rows[index])
        # Write a position for *every* row, not just the two that swapped:
        # a partial ordering would let untouched rows fall to the end, which
        # is not what moving one row up should do.
        for position, (key, *_rest) in enumerate(self.rows):
            self.overrides.setdefault(key, {})["order"] = position
        self._refresh_rows(self.on_reorder)

    def _refresh_rows(self, callback) -> None:
        """Rebuild the dialog, so the list on screen keeps matching the
        order the legend will draw."""
        rows, overrides = self.rows, self.overrides
        on_change, on_reorder = self.on_change, self.on_reorder
        master = self.master
        self.destroy()
        callback()
        LegendEditorDialog(master, rows, overrides, on_change, on_reorder)

    def _reset_all(self) -> None:
        self.overrides.clear()
        self._refresh_rows(self.on_change)
