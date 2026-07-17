"""Experimental LLM assist (dev-only, hidden behind the experimental
features toggle - deliberately not mentioned in the README).

Asks an LLM of the user's choice to write a standalone Python or R
script that recreates the current map, so the mapping workflow can be
audited and reproduced later. Only the map settings and the datasets'
column names are ever sent - no data rows, no coordinates, no category
values. The user supplies their own API key and requests go straight to
the chosen provider. A PNG snapshot of the map can optionally be
attached (off by default).

The generated code is a starting point, not a result: the user must
read it, run it themselves, and compare its output to their map.

This module is UI-free (the dialog lives in pymappr/ui/llm_assist.py)
and uses plain HTTPS JSON via urllib, like the update checker, so the
packaged app gains no dependencies. Three wire formats cover every
provider: Anthropic's Messages API, Google's Gemini API, and the
OpenAI-compatible chat completions API used by everyone else.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from pymappr import __version__
from pymappr.updates import GITHUB_REPO

ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 8192  # Anthropic requires an explicit output cap
DEFAULT_TIMEOUT = 300.0  # reasoning models can take minutes

# Home page credited in the attribution comment PyMappr prepends to the
# generated code.
REPO_URL = f"https://github.com/{GITHUB_REPO}"

# Line-comment syntax for the attribution header. Python and R both use
# "#"; any other language falls back to "#" as the most common marker.
_COMMENT_PREFIXES = {"Python": "#", "R": "#"}


class LLMError(Exception):
    """A provider request failed or returned nothing usable."""


@dataclass(frozen=True)
class Provider:
    """One selectable provider: a wire format plus editable defaults."""

    api: str        # "anthropic" | "openai" | "gemini"
    endpoint: str   # default endpoint URL (editable in the dialog)
    model: str      # default model (the seed; still editable in the dialog)
    key_hint: str   # what the provider's API keys usually look like
    key_url: str = ""  # where to sign up for / manage an API key
    models: tuple[str, ...] = ()  # dropdown suggestions (still editable)


# Mainstream + Chinese providers; anything else fits through the
# OpenAI-compatible custom entry (e.g. Mistral, xAI, or a local server).
# The ``models`` lists seed an editable dropdown - a user can always type a
# model the list doesn't mention. Names and key_url pages checked mid-2026;
# providers rename fast, so treat these as current-at-time-of-writing
# defaults, not gospel.
PROVIDERS: dict[str, Provider] = {
    "Anthropic (Claude)": Provider(
        api="anthropic",
        endpoint="https://api.anthropic.com/v1/messages",
        model="claude-opus-4-8",
        key_hint="sk-ant-...",
        key_url="https://console.anthropic.com/settings/keys",
        models=("claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5",
                "claude-fable-5")),
    "OpenAI (GPT)": Provider(
        api="openai",
        endpoint="https://api.openai.com/v1/chat/completions",
        model="gpt-5.6",
        key_hint="sk-...",
        key_url="https://platform.openai.com/api-keys",
        models=("gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
                "gpt-5.5", "gpt-5.1")),
    "Google (Gemini)": Provider(
        api="gemini",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models",
        model="gemini-3.1-pro-preview",
        key_hint="AIza...",
        key_url="https://aistudio.google.com/apikey",
        models=("gemini-3.1-pro-preview", "gemini-3.5-flash",
                "gemini-3.1-flash-lite", "gemini-2.5-pro",
                "gemini-2.5-flash")),
    "DeepSeek": Provider(
        api="openai",
        endpoint="https://api.deepseek.com/v1/chat/completions",
        model="deepseek-v4-flash",
        key_hint="sk-...",
        key_url="https://platform.deepseek.com/api_keys",
        models=("deepseek-v4-flash", "deepseek-v4-pro")),
    "Qwen (Alibaba DashScope)": Provider(
        api="openai",
        endpoint="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
                 "/chat/completions",
        model="qwen3-max",
        key_hint="sk-...",
        key_url="https://dashscope.console.aliyun.com/apiKey",
        models=("qwen3-max", "qwen-max", "qwen-plus", "qwen-turbo",
                "qwen3-coder-plus")),
    "Kimi (Moonshot)": Provider(
        api="openai",
        endpoint="https://api.moonshot.ai/v1/chat/completions",
        model="kimi-k2.6",
        key_hint="sk-...",
        key_url="https://platform.moonshot.ai/console/api-keys",
        models=("kimi-k2.6", "kimi-k2.7-code", "kimi-k2.5")),
    "GLM (Zhipu / BigModel)": Provider(
        api="openai",
        endpoint="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        model="glm-4.7",
        key_hint="",
        key_url="https://open.bigmodel.cn/usercenter/apikeys",
        models=("glm-4.7", "glm-4.7-flash", "glm-5", "glm-4.6")),
    "Custom (OpenAI-compatible)": Provider(
        api="openai",
        endpoint="",
        model="",
        key_hint="",
        key_url="",
        models=()),
}

LANGUAGES = ("Python", "R")
_TOOLCHAINS = {
    "Python": "Python, using matplotlib with cartopy (or geopandas) "
              "and pandas",
    "R": "R, using ggplot2 with sf and rnaturalearth",
}


def toolchain(language: str) -> str:
    """The libraries hint dropped into the system prompt. Python and R get
    tuned recommendations; any other language the user asks for gets a
    generic, best-effort hint (only Python and R are actually tested)."""
    return _TOOLCHAINS.get(
        language,
        f"{language}, using whatever mapping and plotting libraries are "
        f"idiomatic for {language}")


# ------------------------------------------------------- what gets sent

def _json_scalar(value):
    """Coerce one dataframe cell to a JSON-serialisable scalar; NaN and
    missing values become None, numpy scalars become Python scalars."""
    if value is None:
        return None
    try:
        if value != value:  # NaN (Python or numpy) is never equal to itself
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (bool, int, float, str)):
        return value
    item = getattr(value, "item", None)  # numpy scalar -> Python scalar
    return item() if callable(item) else str(value)


def first_rows(entry, count: int) -> list[dict]:
    """The first *count* rows of a dataset as ``{column label: value}``
    dicts, using the same display column names as :func:`describe_entry`.

    Unlike everything else in this module, this exposes real coordinate
    and category values, so it is only ever called when the user has
    explicitly opted in to sending a data sample (off by default).
    """
    if count <= 0:
        return []
    frame = entry.dataset.frame
    labels = dict(zip(entry.dataset.name_keys, entry.dataset.name_labels))
    labels.update({"lon": "Longitude", "lat": "Latitude"})
    present = [c for c in frame.columns if c in labels]
    rows = []
    for values in frame[present].head(count).itertuples(index=False,
                                                        name=None):
        rows.append({labels[col]: _json_scalar(val)
                     for col, val in zip(present, values)})
    return rows


def describe_entry(entry, sample: int = 0) -> dict:
    """A summary of one dataset: column names and styling choices. With
    *sample* > 0, the first *sample* rows of real data are attached too
    (opt-in); otherwise no values are included. Style entries are keyed by
    group values in the app, so only the color/marker/size triples are
    kept."""
    styles = [{"color": s.color, "marker": s.marker, "size": s.size}
              for _label, s in sorted(entry.styles.items())]
    summary = {
        "name": entry.name,
        "visible": entry.visible,
        "points": len(entry.dataset),
        "name_columns": list(entry.dataset.name_labels),
        "coordinate_columns": ["Longitude", "Latitude"],
        "group_by": entry.group_by or None,
        "color_by": entry.color_by or None,
        "symbol_by": entry.symbol_by or None,
        "vary_symbols": entry.vary_symbols,
        "manually_entered": entry.manual is not None,
        "groups": len(entry.styles),
        "group_styles": styles,
    }
    if sample > 0:
        summary["sample_rows"] = first_rows(entry, sample)
    return summary


def describe_map(state: dict, entries, sample: int = 0) -> dict:
    """Everything the LLM gets to see: the app's collected map state
    with the dataset rows replaced by :func:`describe_entry` summaries,
    and boolean layer dicts flattened to lists of enabled layers.

    *sample* (0 by default) is how many leading rows of each dataset to
    include verbatim; 0 keeps the summary entirely data-free."""
    m = dict(state.get("map", {}))
    enabled = {section: sorted(key for key, on
                               in dict(m.pop(section, {})).items() if on)
               for section in ("lines", "fills", "points", "labels")}
    if sample > 0:
        withheld = (f"Only the first {sample} row(s) of each dataset are "
                    "shared (see sample_rows) for reference; every other "
                    "row is withheld. Load the full data from the user's "
                    "file - do not treat the sample as complete.")
    else:
        withheld = ("Data rows, coordinates, and category values were "
                    "deliberately not shared; only column names and "
                    "settings.")
    return {
        "generator": f"PyMappr {__version__}",
        "map": m,
        "enabled_layers": enabled,
        "legend": dict(state.get("legend", {})),
        "point_alpha": state.get("point_alpha"),
        "view": dict(state.get("view", {})),
        "datasets": [describe_entry(e, sample) for e in entries],
        "withheld": withheld,
    }


def build_prompt(summary: dict, language: str, extra: str = "",
                 with_image: bool = False,
                 with_sample: bool = False) -> tuple[str, str]:
    """The (system, user) texts sent to the provider, verbatim."""
    data_rule = (
        "- Only a small sample of the first data rows is included for "
        "reference; the full dataset was NOT shared. Never invent "
        "example data or treat the sample as complete; load everything "
        "from the user's file.\n"
        if with_sample else
        "- The data rows, coordinates, and category values were "
        "deliberately NOT shared with you. Never invent example data; "
        "load everything from the user's file.\n")
    system = (
        "You are helping a researcher document a map they made in "
        f"PyMappr, a desktop point-distribution mapping application. "
        f"Write a complete, standalone script in {toolchain(language)} "
        "that recreates the map from the settings provided, so the "
        "workflow can be audited and reproduced later.\n\n"
        "Requirements:\n"
        "- The script must run as-is once the user fills in clearly "
        "marked placeholders (path to their data file, exact column "
        "names, group values for the legend).\n"
        + data_rule +
        "- Recreate the projection (including any custom origin), map "
        "extent, base layers, point styling, and legend as described.\n"
        "- Comment the script so another researcher can audit each "
        "step, and state any assumptions in comments at the top.\n"
        "- Reply with only the script, in a single code block.")
    user = ("Recreate this map.\n\nMap configuration (JSON):\n"
            + json.dumps(summary, indent=2, sort_keys=True))
    if with_image:
        user += ("\n\nA PNG snapshot of the rendered map is attached "
                 "for reference.")
    if extra.strip():
        user += "\n\nAdditional notes from the user:\n" + extra.strip()
    return system, user


def attribution_comment(language: str, model: str) -> str:
    """PyMappr's credit line for LLM-generated code, in the target
    language's line-comment syntax. Names both tools and their versions:
    PyMappr's own version and the LLM model id (e.g. "claude-opus-4-8").
    PyMappr adds this itself rather than trusting the model to."""
    prefix = _COMMENT_PREFIXES.get(language, "#")
    return (f"{prefix} Made with PyMappr {__version__} + "
            f"{model or 'an LLM'} - {REPO_URL}")


def prepend_attribution(code: str, language: str, model: str) -> str:
    """The generated code with the attribution comment as its first line
    (kept after a shebang, if the script starts with one, so it stays
    executable)."""
    comment = attribution_comment(language, model)
    if code.startswith("#!"):
        shebang, _, rest = code.partition("\n")
        return f"{shebang}\n{comment}\n{rest}"
    return f"{comment}\n{code}"


# -------------------------------------------------------- wire formats

def build_request(api: str, endpoint: str, model: str, api_key: str,
                  system: str, user: str,
                  image_png: bytes | None = None):
    """Build one provider request; returns (url, headers, body bytes)."""
    b64 = (base64.b64encode(image_png).decode("ascii")
           if image_png else None)
    if api == "anthropic":
        content: list[dict] = []
        if b64:
            content.append({"type": "image",
                            "source": {"type": "base64",
                                       "media_type": "image/png",
                                       "data": b64}})
        content.append({"type": "text", "text": user})
        body = {"model": model, "max_tokens": MAX_TOKENS,
                "system": system,
                "messages": [{"role": "user", "content": content}]}
        headers = {"content-type": "application/json",
                   "x-api-key": api_key,
                   "anthropic-version": ANTHROPIC_VERSION}
        url = endpoint
    elif api == "gemini":
        parts: list[dict] = [{"text": user}]
        if b64:
            parts.append({"inline_data": {"mime_type": "image/png",
                                          "data": b64}})
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}]}
        headers = {"content-type": "application/json",
                   "x-goog-api-key": api_key}
        # The default endpoint is the models base; a pasted full URL
        # (already naming the model and method) is used as-is.
        url = (endpoint if ":generateContent" in endpoint
               else f"{endpoint.rstrip('/')}/{model}:generateContent")
    elif api == "openai":
        if b64:
            user_content: object = [
                {"type": "text", "text": user},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}}]
        else:
            user_content = user
        body = {"model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user_content}]}
        headers = {"content-type": "application/json"}
        if api_key:  # local OpenAI-compatible servers may not need one
            headers["authorization"] = f"Bearer {api_key}"
        url = endpoint
    else:
        raise LLMError(f"Unknown API kind: {api!r}")
    return url, headers, json.dumps(body).encode("utf-8")


def parse_response(api: str, payload: dict) -> str:
    """The model's reply text from one provider response payload."""
    try:
        if api == "anthropic":
            if payload.get("stop_reason") == "refusal":
                raise LLMError("The model declined this request "
                               "(stop_reason: refusal).")
            text = "".join(block.get("text", "")
                           for block in payload.get("content", [])
                           if block.get("type") == "text")
        elif api == "gemini":
            candidates = payload.get("candidates")
            if not candidates:
                feedback = payload.get("promptFeedback", {})
                raise LLMError("The model returned no reply"
                               + (f" (blocked: {feedback['blockReason']})"
                                  if feedback.get("blockReason") else "")
                               + ".")
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts)
        elif api == "openai":
            message = payload["choices"][0]["message"]
            text = message.get("content") or ""
        else:
            raise LLMError(f"Unknown API kind: {api!r}")
    except LLMError:
        raise
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(
            f"Unexpected response from the provider: {exc}") from exc
    if not text.strip():
        raise LLMError("The model returned an empty reply.")
    return text


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    """A readable message from an HTTP error body (providers return
    JSON error envelopes in a couple of shapes)."""
    try:
        payload = json.loads(exc.read().decode("utf-8", "replace"))
        error = payload.get("error", payload)
        if isinstance(error, dict):
            return str(error.get("message") or error)
        return str(error)
    except Exception:  # noqa: BLE001 - any body is better than none
        return exc.reason if isinstance(exc.reason, str) else str(exc)


def generate_code(api: str, endpoint: str, model: str, api_key: str,
                  system: str, user: str,
                  image_png: bytes | None = None,
                  timeout: float = DEFAULT_TIMEOUT) -> str:
    """Send one request to the provider and return the reply text.

    Blocking - the dialog calls this from a worker thread. Raises
    :class:`LLMError` with a readable message on any failure.
    """
    url, headers, body = build_request(api, endpoint, model, api_key,
                                       system, user, image_png)
    if not url.lower().startswith(("http://", "https://")):
        raise LLMError(f"Not a valid endpoint URL: {url!r}")
    request = urllib.request.Request(
        url, data=body,
        headers={**headers, "user-agent": f"PyMappr/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise LLMError(
            f"HTTP {exc.code}: {_http_error_message(exc)}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Could not reach the provider: "
                       f"{exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise LLMError(str(exc)) from exc
    return parse_response(api, payload)


def extract_code(reply: str) -> str:
    """The first fenced code block of a reply (for saving to a file),
    or the whole reply when the model didn't use a fence."""
    match = re.search(r"```[^\n]*\n(.*?)```", reply, re.DOTALL)
    return match.group(1).strip() if match else reply.strip()
