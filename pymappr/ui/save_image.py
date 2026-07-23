"""Save-map-as dialog: pick an image format, resolution and DPI.

Replaces the old one-click "Save map as PNG" / "Save map as TIFF"
buttons with a single "Save map as..." entry point. The map keeps its
on-screen geometry (a fixed size in inches); the chosen DPI sets how many
pixels that becomes, shown live as the output resolution.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# (label, short format key, default extension). The key is what the
# renderer dispatches on; the extension seeds the save dialog.
FORMATS = [
    ("PNG image", "png", ".png"),
    ("JPEG image", "jpg", ".jpg"),
    ("TIFF image", "tiff", ".tif"),
    ("PDF document", "pdf", ".pdf"),
    ("SVG vector", "svg", ".svg"),
    ("WebP image", "webp", ".webp"),
]
# Vector formats scale without pixels, so DPI only affects any embedded
# raster and there is no fixed output resolution to report.
VECTOR_FORMATS = {"pdf", "svg"}
DPI_CHOICES = ["100", "150", "200", "300", "600"]


class SaveImageDialog(tk.Toplevel):
    """Choose format + resolution/DPI, then write the map to disk."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("Save map as")
        self.transient(master)
        self.resizable(False, False)

        self._labels = [label for label, _key, _ext in FORMATS]
        self._by_label = {label: (key, ext)
                          for label, key, ext in FORMATS}

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        row = ttk.Frame(body)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Format:", width=12).pack(side="left")
        self._format_var = tk.StringVar(value=self._labels[0])
        format_box = ttk.Combobox(row, textvariable=self._format_var,
                                  state="readonly", values=self._labels,
                                  width=18)
        format_box.pack(side="right")
        format_box.bind("<<ComboboxSelected>>",
                        lambda _e: self._update_resolution())

        row = ttk.Frame(body)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="DPI:", width=12).pack(side="left")
        stored = str(self.app.panel.dpi_var.get()) or "200"
        self._dpi_var = tk.StringVar(value=stored)
        dpi_box = ttk.Combobox(row, textvariable=self._dpi_var,
                               values=DPI_CHOICES, width=18)
        dpi_box.pack(side="right")
        dpi_box.bind("<<ComboboxSelected>>",
                     lambda _e: self._update_resolution())
        dpi_box.bind("<KeyRelease>", lambda _e: self._update_resolution())

        row = ttk.Frame(body)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Resolution:", width=12).pack(side="left")
        self._resolution = ttk.Label(row, text="", foreground="#666666")
        self._resolution.pack(side="right")

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Save\N{HORIZONTAL ELLIPSIS}",
                   command=self._save).pack(side="right")
        ttk.Button(buttons, text="Cancel",
                   command=self.destroy).pack(side="right", padx=(0, 6))

        self.bind("<Escape>", lambda _e: self.destroy())
        self._update_resolution()
        self.update_idletasks()
        self.grab_set()

    # ------------------------------------------------------------- helpers

    def _dpi(self) -> int | None:
        try:
            dpi = int(float(self._dpi_var.get()))
        except (TypeError, ValueError):
            return None
        return dpi if dpi > 0 else None

    def _figure_size(self) -> tuple[float, float] | None:
        # The saved image size, cropped to the map for a portrait
        # (letterboxed) orientation rather than the on-screen figure.
        try:
            width, height = self.app.renderer.export_size_inches()
            return float(width), float(height)
        except Exception:  # noqa: BLE001 - no renderer / unusual state
            return None

    def _update_resolution(self) -> None:
        key = self._by_label[self._format_var.get()][0]
        if key in VECTOR_FORMATS:
            self._resolution.config(text="vector (scales without pixels)")
            return
        dpi = self._dpi()
        size = self._figure_size()
        if dpi is None or size is None:
            self._resolution.config(text="\N{EM DASH}")
            return
        width = int(round(size[0] * dpi))
        height = int(round(size[1] * dpi))
        self._resolution.config(text=f"{width} \N{MULTIPLICATION SIGN} "
                                     f"{height} px")

    # ---------------------------------------------------------------- save

    def _save(self) -> None:
        dpi = self._dpi()
        if dpi is None:
            messagebox.showerror("Save map as",
                                 "Enter a positive whole-number DPI.",
                                 parent=self)
            return
        key, extension = self._by_label[self._format_var.get()]
        label = self._format_var.get()
        path = filedialog.asksaveasfilename(
            parent=self, title="Save map as",
            defaultextension=extension,
            initialfile="map" + extension,
            filetypes=[(label, "*" + extension), ("All files", "*.*")])
        if not path:
            return
        # Persist the chosen DPI as the project's default.
        self.app.panel.dpi_var.set(str(dpi))
        self.app._busy(True)
        try:
            self.app.renderer.save_image(path, fmt=key, dpi=dpi)
        except Exception as exc:  # noqa: BLE001 - show any save error
            self.app._busy(False)
            messagebox.showerror("Could not save map", str(exc),
                                 parent=self)
            return
        self.app._busy(False)
        self.app.set_status(f"Saved map to {path}")
        self.destroy()
