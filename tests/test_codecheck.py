import pytest

from pymappr import codecheck


# --------------------------------------------------------------- python

def test_valid_python_passes():
    code = "import pandas as pd\n\nprint(pd.DataFrame())\n"
    assert codecheck.validate_python(code) == []


def test_python_syntax_error_reports_line():
    issues = codecheck.validate_python("import io\n\ndef broken(:\n")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].line == 3
    assert "syntax error" in issues[0].message


def test_empty_python_is_an_error():
    issues = codecheck.validate_python("   \n\n")
    assert codecheck.has_errors(issues)


def test_python_without_imports_warns():
    issues = codecheck.validate_python("x = 1\nprint(x)\n")
    assert [i.severity for i in issues] == ["warning"]
    assert not codecheck.has_errors(issues)


# -------------------------------------------------------------------- R

def test_valid_r_passes():
    code = (
        "# a comment with an unbalanced ( bracket\n"
        "library(sf)\n"
        'x <- c(1, 2, 3)  # trailing note )\n'
        's <- "a string with ) inside"\n'
        "t <- 'and one with ('\n"
        "`odd (name` <- 42\n"
        "f <- function(a) {\n"
        "  if (a > 1) a else -a\n"
        "}\n"
    )
    assert codecheck.validate_r(code) == []


def test_r_unclosed_bracket():
    issues = codecheck.validate_r("f <- function(a) { a + 1\n")
    assert codecheck.has_errors(issues)
    assert any("Unclosed '{'" in i.message for i in issues)
    assert issues[0].line == 1


def test_r_mismatched_and_extra_brackets():
    issues = codecheck.validate_r("x <- c(1]\n")
    assert any("Mismatched" in i.message for i in issues)
    issues = codecheck.validate_r("x <- 1)\n")
    assert any("Unmatched closing" in i.message for i in issues)


def test_r_unclosed_string():
    issues = codecheck.validate_r('x <- "never closed\ny <- 1\n')
    assert codecheck.has_errors(issues)
    assert any("Unclosed string" in i.message for i in issues)


def test_r_escapes_and_raw_strings():
    code = (
        'a <- "escaped \\" quote ("\n'
        'b <- r"(raw with ( unbalanced)"\n'
        "c <- a\n"
    )
    assert codecheck.validate_r(code) == []


def test_r_empty_is_an_error():
    assert codecheck.has_errors(codecheck.validate_r(""))


# ---------------------------------------------------------- placeholders

def test_find_placeholders():
    code = (
        "# TODO: set the path\n"
        'path <- "<your file here>"\n'
        'other <- "path/to/data.csv"\n'
        "fine <- 1\n"
    )
    issues = codecheck.find_placeholders(code)
    assert [i.line for i in issues] == [1, 2, 3]
    assert all(i.severity == "warning" for i in issues)


# -------------------------------------------------------------- dispatch

def test_validate_code_dispatch_and_order():
    issues = codecheck.validate_code("Python", "# TODO later\ndef f(:\n")
    # Errors are listed before warnings.
    assert issues[0].severity == "error"
    assert issues[-1].severity == "warning"
    assert codecheck.validate_code("R", "x <- c(1)\n") == []
    with pytest.raises(ValueError):
        codecheck.validate_code("Fortran", "print *, 'hi'")


def test_summarize():
    clean = codecheck.summarize("Python", [])
    assert "passed" in clean and "syntax check only" in clean
    issues = codecheck.validate_code("Python", "def f(:\n")
    text = codecheck.summarize("Python", issues)
    assert "1 error" in text and "line 1" in text
