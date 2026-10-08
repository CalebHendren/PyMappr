"""Config values written as Python and R source, and the pieces both
scripts share: the attribution link and the pre-made function templates."""

from __future__ import annotations

import math
import numbers
import re
from functools import lru_cache
from pathlib import Path

from pymappr.updates import GITHUB_REPO

# Home page for the attribution comment at the top of every script.
REPO_URL = f"https://github.com/{GITHUB_REPO}"

# ggplot2 linetype names approximating the renderer's dash tuples.
_R_LINETYPES = {
    (0, (1, 2)): "dotted",
    (0, (3, 2)): "dashed",
    (0, (3, 3)): "dashed",
    (0, (4, 2)): "dashed",
    (0, (5, 3)): "longdash",
    (0, (6, 3)): "longdash",
}


# The pre-made functions pasted verbatim below every script's configuration
# block. They replicate pymappr/renderer/ for a single static view, and live
# in real .py/.R files so editors, linters and diffs treat them as code.
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=None)
def _template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _py(value) -> str:
    """A Python literal for a config value, containers included.

    Floats are rounded to 6 places; NaN and infinity, which repr() would
    write as the undefined names ``nan`` and ``inf``, become ``float()``
    calls.
    """
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, numbers.Integral):
        return repr(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return 'float("nan")'
        if math.isinf(number):
            return 'float("inf")' if number > 0 else '-float("inf")'
        return repr(round(number, 6))
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_py(k)}: {_py(v)}"
                               for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_py(item) for item in value) + "]"
    if isinstance(value, tuple):
        items = [_py(item) for item in value]
        return "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"
    if isinstance(value, str):
        # Dropped like the R export does, so a label and the embedded data
        # it must match (pandas stops a CSV field at a NUL) agree.
        return repr(value.replace("\x00", ""))
    return repr(value)


def _r(value) -> str:
    """An R literal for a config value. NaN and infinity become R's own
    ``NA_real_``, ``Inf`` and ``-Inf`` rather than undefined names."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return "NA_real_"
        if math.isinf(number):
            return "Inf" if number > 0 else "-Inf"
        return repr(round(number, 6))
    # An R string cannot hold a NUL, not even escaped, so it is dropped.
    text = str(value).replace("\x00", "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", "\\n").replace("\r", "").replace("\t", "\\t")
    return f'"{text}"'


def _comment_text(text) -> str:
    """*text* made safe for a one-line ``#`` comment in either language: a
    line break in it would end the comment and run the rest as code, and
    neither language accepts a NUL in its source."""
    text = str(text).replace("\x00", "")
    return re.sub(r"[\r\n]+", " ", text).strip()


def _r_named(pairs: list[tuple[str, str]], indent: str) -> str:
    """An R c(...) or list(...) body: one `name = value` per line."""
    inner = f",\n{indent}".join(f"{_r(name)} = {value}"
                                for name, value in pairs)
    return f"\n{indent}{inner}\n{indent[:-2]}"


def _size_mm(area: float) -> float:
    """Matplotlib scatter area (points^2) -> approximate ggplot2 size."""
    return round(max(math.sqrt(max(area, 1.0)) / 2.845, 0.3), 2)


def _linewidth_mm(width: float) -> float:
    """Matplotlib line width (points) -> approximate ggplot2 linewidth."""
    return round(max(width / 2.13, 0.05), 2)


def _r_linetype(linestyle) -> str:
    if isinstance(linestyle, tuple):
        return _R_LINETYPES.get(
            (linestyle[0], tuple(linestyle[1])), "dashed")
    return "solid"


def _safe_name(name: str) -> str:
    """A project name on one line and free of double quotes, so it can sit
    in quotes in a docstring, comment or README."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(name)).replace('"', "'")
    return text.strip() or "map"


def _wrapped_items(items: list[str], indent: str, width: int = 78
                   ) -> list[str]:
    """*items* joined by ", " over as many lines as keep them under
    *width*, each line starting with *indent*."""
    lines, line = [], ""
    for item in items:
        candidate = f"{line}, {item}" if line else item
        if line and len(indent) + len(candidate) + 1 > width:
            lines.append(indent + line + ",")
            line = item
        else:
            line = candidate
    if line:
        lines.append(indent + line)
    return lines
