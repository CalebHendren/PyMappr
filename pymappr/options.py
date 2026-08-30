"""Shared plumbing for the settings dataclasses.

:class:`~pymappr.legend.LegendOptions`, and the scale bar and compass
options in :mod:`pymappr.decorations`, all travel the same road: the control
panel fills them in, the renderer reads them, and :mod:`pymappr.projects`
writes them to a project file as a plain dict. Loading one back has to survive
two kinds of drift - a project written before a field existed, and a project
written after a field was dropped - so the reader defaults what is missing and
ignores what it no longer knows.

Keeping that in one place means a new options dataclass is a list of fields
rather than another copy of ``from_dict``.
"""

from __future__ import annotations

from dataclasses import fields

__all__ = ["UNSET", "coerce_value", "values_from_dict"]

UNSET = object()


def coerce_value(value, annotation):
    """*value* as the type its field declares, or :data:`UNSET` when it cannot
    be read that way and the dataclass default should stand.

    Annotations are strings here (every module uses
    ``from __future__ import annotations``), so this matches on the text
    rather than on the type object.
    """
    text = str(annotation)
    optional = "None" in text
    if value is None:
        return None if optional else UNSET
    try:
        if text.startswith("bool"):
            return bool(value)
        if text.startswith("int"):
            return int(float(value))
        if text.startswith("float"):
            return float(value)
        return str(value)
    except (TypeError, ValueError):
        return UNSET


def values_from_dict(cls, data: dict | None) -> dict:
    """The keyword arguments for *cls* drawn from a stored dict.

    Unknown keys are dropped and unreadable values fall back to the field
    default, so the caller can always write
    ``cls(**values_from_dict(cls, data))``.
    """
    data = dict(data or {})
    values = {}
    for field in fields(cls):
        if field.name not in data:
            continue
        coerced = coerce_value(data[field.name], field.type)
        if coerced is not UNSET:
            values[field.name] = coerced
    return values
