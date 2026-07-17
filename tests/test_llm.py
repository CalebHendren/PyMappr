import json

import pytest

from pymappr import llm
from pymappr.data_loader import build_manual_dataset
from pymappr.projects import DatasetEntry
from pymappr.styles import PointStyle


def make_entry():
    dataset = build_manual_dataset(
        "spiders.csv", "38,-100, Secret Site\n-25,140, Hidden Spring\n")
    return DatasetEntry(
        dataset=dataset, name="spiders.csv", visible=True,
        group_by="Legend", color_by="", symbol_by="Label",
        vary_symbols=True,
        styles={"Confidential locality": PointStyle(color="#123456",
                                                    marker="Star",
                                                    size=45.0)})


def make_state():
    return {
        "datasets": [{"rows": [["Secret Site", -100.0, 38.0]]}],
        "active": 0,
        "map": {
            "projection": "Robinson", "proj_lon0": "", "proj_lat0": "",
            "basemap": "simple", "continent": "World",
            "compass": True, "graticule": "5\N{DEGREE SIGN}",
            "hide_grid_labels": False, "line_width": 1.0, "dpi": "200",
            "ocean": "blue", "lake_fill": "none", "bathymetry": False,
            "capitals_only": False,
            "lines": {"countries": True, "rivers": False},
            "fills": {"land": False},
            "points": {"cities": True},
            "labels": {"countries": False},
        },
        "legend": {"show": True, "frame": True, "location": "best",
                   "fontsize": "8", "columns": "1", "title": ""},
        "point_alpha": 0.9,
        "view": {"xlim": [-180, 180], "ylim": [-90, 90]},
    }


# ------------------------------------------------------------ providers

def test_provider_registry():
    assert len(llm.PROVIDERS) == 8
    assert "Anthropic (Claude)" in llm.PROVIDERS
    assert "DeepSeek" in llm.PROVIDERS  # Chinese providers included
    for name, provider in llm.PROVIDERS.items():
        assert provider.api in ("anthropic", "openai", "gemini"), name
        if name != "Custom (OpenAI-compatible)":
            assert provider.endpoint.startswith("https://"), name
            assert provider.model, name
            # Every named provider links to where you get an API key.
            assert provider.key_url.startswith("https://"), name
    # The custom (bring-your-own-endpoint) entry has no fixed key page.
    assert llm.PROVIDERS["Custom (OpenAI-compatible)"].key_url == ""


# ----------------------------------------------------- what may be sent

def test_describe_map_excludes_data_values():
    summary = llm.describe_map(make_state(), [make_entry()])
    dumped = json.dumps(summary)
    # No rows, coordinates, per-point labels, or group values...
    for secret in ("Secret Site", "Hidden Spring", "-100", "140",
                   "Confidential locality"):
        assert secret not in dumped
    # ...but column names, style, and map settings are included.
    dataset = summary["datasets"][0]
    assert dataset["name_columns"] == ["Legend", "Label"]
    assert dataset["points"] == 2
    assert dataset["group_styles"] == [
        {"color": "#123456", "marker": "Star", "size": 45.0}]
    assert summary["map"]["projection"] == "Robinson"
    assert summary["enabled_layers"]["lines"] == ["countries"]
    assert summary["enabled_layers"]["points"] == ["cities"]
    assert "withheld" in summary


def test_describe_map_can_include_sample_rows():
    # Opt-in: the first N rows of real data are attached, with the display
    # column names, and the withheld note changes to say so.
    summary = llm.describe_map(make_state(), [make_entry()], sample=1)
    dataset = summary["datasets"][0]
    assert dataset["sample_rows"] == [
        {"Legend": "spiders.csv", "Label": "Secret Site",
         "Longitude": -100.0, "Latitude": 38.0}]
    # Only the first row is shared; the second stays withheld.
    dumped = json.dumps(summary)
    assert "Secret Site" in dumped
    assert "Hidden Spring" not in dumped
    assert "sample_rows" in summary["withheld"]
    # The summary is still JSON-serialisable (no stray numpy scalars).
    json.dumps(summary)


def test_describe_map_default_shares_no_rows():
    summary = llm.describe_map(make_state(), [make_entry()])
    assert "sample_rows" not in summary["datasets"][0]
    assert "deliberately not shared" in summary["withheld"]


def test_first_rows_caps_and_off():
    entry = make_entry()  # two rows
    assert llm.first_rows(entry, 0) == []
    assert len(llm.first_rows(entry, 1)) == 1
    assert len(llm.first_rows(entry, 5)) == 2  # capped at what exists


def test_build_prompt_sample_instruction():
    summary = llm.describe_map(make_state(), [make_entry()], sample=3)
    system, _user = llm.build_prompt(summary, "Python", with_sample=True)
    assert "small sample" in system
    assert "load everything from the user's file" in system
    # Without the flag the strict "not shared" wording is used.
    system_off, _user = llm.build_prompt(summary, "Python")
    assert "deliberately NOT shared" in system_off


def test_build_prompt_leaves_attribution_to_pymappr():
    # PyMappr adds the credit line itself, so the prompt no longer asks
    # the model to include one.
    summary = llm.describe_map(make_state(), [make_entry()])
    system, _user = llm.build_prompt(summary, "Python")
    assert "attribution" not in system.lower()
    assert "Made with PyMappr" not in system


def test_prepend_attribution_adds_credit_comment():
    code = llm.prepend_attribution("print('hi')\n", "Python", "gpt-5.6")
    assert code.splitlines()[0] == (
        f"# Made with PyMappr {llm.__version__} + gpt-5.6 - {llm.REPO_URL}")
    # Falls back gracefully when the model is somehow blank.
    assert "an LLM" in llm.attribution_comment("R", "")
    # A shebang stays first so the script remains executable; the credit
    # follows it.
    shebang = llm.prepend_attribution("#!/usr/bin/env python3\nx = 1\n",
                                      "Python", "gpt-5.6")
    lines = shebang.splitlines()
    assert lines[0] == "#!/usr/bin/env python3"
    assert lines[1].startswith("# Made with PyMappr")


def test_build_prompt_mentions_language_and_notes():
    summary = llm.describe_map(make_state(), [make_entry()])
    system, user = llm.build_prompt(summary, "R",
                                    extra="Column 1 is the species.",
                                    with_image=True)
    assert "ggplot2" in system
    assert "NOT shared" in system
    assert "Robinson" in user
    assert "Column 1 is the species." in user
    assert "PNG snapshot" in user
    _system, user = llm.build_prompt(summary, "Python")
    assert "PNG snapshot" not in user


# --------------------------------------------------------- wire formats

def test_build_request_anthropic():
    url, headers, body = llm.build_request(
        "anthropic", "https://api.anthropic.com/v1/messages",
        "claude-opus-4-8", "sk-ant-test", "sys", "usr",
        image_png=b"\x89PNG")
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == "2023-06-01"
    payload = json.loads(body)
    assert payload["model"] == "claude-opus-4-8"
    assert payload["max_tokens"] > 0
    assert payload["system"] == "sys"
    content = payload["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[-1] == {"type": "text", "text": "usr"}

    _url, _headers, body = llm.build_request(
        "anthropic", "https://api.anthropic.com/v1/messages",
        "claude-opus-4-8", "sk-ant-test", "sys", "usr")
    content = json.loads(body)["messages"][0]["content"]
    assert [block["type"] for block in content] == ["text"]


def test_build_request_openai():
    url, headers, body = llm.build_request(
        "openai", "https://api.deepseek.com/v1/chat/completions",
        "deepseek-chat", "sk-test", "sys", "usr")
    assert url.endswith("/chat/completions")
    assert headers["authorization"] == "Bearer sk-test"
    payload = json.loads(body)
    assert payload["messages"][0] == {"role": "system", "content": "sys"}
    assert payload["messages"][1] == {"role": "user", "content": "usr"}

    _url, headers, body = llm.build_request(
        "openai", "http://localhost:11434/v1/chat/completions",
        "llama3", "", "sys", "usr", image_png=b"\x89PNG")
    assert "authorization" not in headers  # keyless local server
    user = json.loads(body)["messages"][1]["content"]
    assert user[0] == {"type": "text", "text": "usr"}
    assert user[1]["image_url"]["url"].startswith(
        "data:image/png;base64,")


def test_build_request_gemini():
    url, headers, body = llm.build_request(
        "gemini", "https://generativelanguage.googleapis.com/v1beta"
                  "/models",
        "gemini-2.5-pro", "AIza-test", "sys", "usr", image_png=b"\x89PNG")
    assert url.endswith("/models/gemini-2.5-pro:generateContent")
    assert headers["x-goog-api-key"] == "AIza-test"
    payload = json.loads(body)
    assert payload["system_instruction"]["parts"] == [{"text": "sys"}]
    parts = payload["contents"][0]["parts"]
    assert parts[0] == {"text": "usr"}
    assert parts[1]["inline_data"]["mime_type"] == "image/png"

    # A pasted full URL (already naming model and method) is kept as-is.
    url, _headers, _body = llm.build_request(
        "gemini", "https://example.com/v1beta/models/x:generateContent",
        "ignored", "k", "sys", "usr")
    assert url == "https://example.com/v1beta/models/x:generateContent"


def test_build_request_unknown_api():
    with pytest.raises(llm.LLMError):
        llm.build_request("smoke-signals", "https://x", "m", "k",
                          "sys", "usr")


# ------------------------------------------------------------ responses

def test_parse_response_anthropic():
    payload = {"stop_reason": "end_turn",
               "content": [{"type": "thinking", "thinking": ""},
                           {"type": "text", "text": "library(sf)"}]}
    assert llm.parse_response("anthropic", payload) == "library(sf)"
    with pytest.raises(llm.LLMError, match="refusal"):
        llm.parse_response("anthropic", {"stop_reason": "refusal",
                                         "content": []})


def test_parse_response_openai():
    payload = {"choices": [{"message": {"content": "import pandas"}}]}
    assert llm.parse_response("openai", payload) == "import pandas"
    with pytest.raises(llm.LLMError):
        llm.parse_response("openai", {"choices": []})
    with pytest.raises(llm.LLMError, match="empty"):
        llm.parse_response("openai",
                           {"choices": [{"message": {"content": None}}]})


def test_parse_response_gemini():
    payload = {"candidates": [{"content": {"parts": [{"text": "x <- 1"}]}}]}
    assert llm.parse_response("gemini", payload) == "x <- 1"
    with pytest.raises(llm.LLMError, match="SAFETY"):
        llm.parse_response("gemini", {"promptFeedback":
                                      {"blockReason": "SAFETY"}})


def test_extract_code():
    reply = ("Here you go:\n```python\nimport pandas as pd\n```\n"
             "Verify it yourself.")
    assert llm.extract_code(reply) == "import pandas as pd"
    assert llm.extract_code("plain text") == "plain text"
