"""Filter bar shown below the map canvas.

Pick a name column and tick the values to show: unticked values are
hidden from the map. With the felines-and-canines sample, filtering by
Family and unticking Felines leaves only the dogs on the map.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

STRIP_HEIGHT = 30


class FilterBar(ttk.Frame):
    """Owns the filter state; calls *on_change* whenever it changes."""

    def __init__(self, master, on_change):
        super().__init__(master)
        self.on_change = on_change
        self._frame = None  # the loaded dataset's DataFrame
        self._column_keys: dict[str, str] = {}  # display label -> column key
        self._value_vars: dict[str, tk.BooleanVar] = {}

        row = ttk.Frame(self, padding=(6, 2))
        row.pack(fill="x")

        ttk.Label(row, text="Filter by:").pack(side="left")
        self.column_var = tk.StringVar(value="None")
        self.column_box = ttk.Combobox(row, textvariable=self.column_var,
                                       state="disabled", values=["None"],
                                       width=14)
        self.column_box.pack(side="left", padx=(4, 8))
        self.column_box.bind("<<ComboboxSelected>>",
                             lambda _e: self._on_column())

        self.all_button = ttk.Button(row, text="All", width=5,
                                     state="disabled",
                                     command=lambda: self._set_all(True))
        self.all_button.pack(side="left")
        self.none_button = ttk.Button(row, text="None", width=6,
                                      state="disabled",
                                      command=lambda: self._set_all(False))
        self.none_button.pack(side="left", padx=(2, 8))

        # Value checkbuttons live in a horizontally scrollable strip so
        # datasets with many values (e.g. ~90 dog breeds) stay usable.
        self._canvas = tk.Canvas(row, height=STRIP_HEIGHT,
                                 highlightthickness=0)
        self._canvas.pack(side="left", fill="x", expand=True)
        self._strip = ttk.Frame(self._canvas)
        self._canvas.create_window((0, 0), window=self._strip, anchor="w",
                                   height=STRIP_HEIGHT)
        self._strip.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._scroll = ttk.Scrollbar(self, orient="horizontal",
                                     command=self._canvas.xview)
        self._canvas.configure(xscrollcommand=self._scroll.set)
        self._scroll.pack(fill="x", padx=6)
        self._bind_wheel_scroll()

    # ------------------------------------------------------------------ API

    def set_dataset(self, frame, name_labels: list[str],
                    name_keys: list[str]) -> None:
        """Point the bar at a newly loaded dataset; resets any filter."""
        self._frame = frame
        self._column_keys = dict(zip(name_labels, name_keys))
        state = "readonly" if len(frame) else "disabled"
        self.column_box.configure(values=["None"] + list(name_labels),
                                  state=state)
        self.column_var.set("None")
        self._rebuild_values()

    def selection(self) -> tuple[str, set[str]] | None:
        """(column key, values to show), or None when no filter is active."""
        key = self._column_keys.get(self.column_var.get())
        if key is None or not self._value_vars:
            return None
        return key, {value for value, var in self._value_vars.items()
                     if var.get()}

    # ------------------------------------------------------------- internal

    def _on_column(self) -> None:
        self._rebuild_values()
        self.on_change()

    def _rebuild_values(self) -> None:
        for child in self._strip.winfo_children():
            child.destroy()
        self._value_vars = {}

        key = self._column_keys.get(self.column_var.get())
        active = (self._frame is not None and key is not None
                  and key in self._frame.columns)
        state = "normal" if active else "disabled"
        self.all_button.configure(state=state)
        self.none_button.configure(state=state)
        if not active:
            self._canvas.xview_moveto(0)
            return

        values = list(dict.fromkeys(self._frame[key].fillna("")))
        for value in values:
            var = tk.BooleanVar(value=True)
            check = ttk.Checkbutton(self._strip,
                                    text=value if value else "(blank)",
                                    variable=var, command=self.on_change)
            check.pack(side="left", padx=(0, 6))
            self._bind_wheel(check)
            self._value_vars[value] = var
        self._canvas.xview_moveto(0)

    def _set_all(self, on: bool) -> None:
        for var in self._value_vars.values():
            var.set(on)
        self.on_change()

    def _bind_wheel_scroll(self) -> None:
        def on_wheel(event):
            delta = -1 if (event.num == 4 or event.delta > 0) else 1
            self._canvas.xview_scroll(delta, "units")

        self._on_wheel = on_wheel
        self._bind_wheel(self._canvas)
        self._bind_wheel(self._strip)

    def _bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_wheel)
        widget.bind("<Button-4>", self._on_wheel)
        widget.bind("<Button-5>", self._on_wheel)
