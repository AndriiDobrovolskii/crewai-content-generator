"""Unit tests for content_generator.tools.parsers.

Each test guards against a specific regression described in the bug IDs below.
No real filesystem writes outside tempfile; no real HTTP or Gemini API calls.
"""

import os
import re
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from content_generator.tools.parsers import (
    _MD_ITALIC_RE,
    _extract_pdf_with_gemini,
    extract_text_from_md,
    _normalize_markdown,
)


# ---------------------------------------------------------------------------
# BUG-04 – Regex catastrophic backtracking
# ---------------------------------------------------------------------------

def test_bug04_md_italic_re_completes_under_10ms_on_100_unmatched_asterisks():
    """BUG-04: _MD_ITALIC_RE must not catastrophically backtrack on a long
    string of unmatched asterisks, which previously caused multi-second hangs.
    The regex must finish in under 10 ms for 100 asterisks.
    """
    pathological = "*" * 100  # Triggers exponential backtracking in naive patterns
    start = time.perf_counter()
    _MD_ITALIC_RE.sub("", pathological)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 10, (
        f"_MD_ITALIC_RE took {elapsed_ms:.1f} ms on 100 unmatched asterisks "
        "(expected < 10 ms).  Likely catastrophic backtracking."
    )


def test_bug04_md_italic_re_strips_real_italic_correctly():
    """BUG-04 (positive case): _MD_ITALIC_RE must still strip genuine italic syntax."""
    result = _MD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), "*hello world*")
    assert "hello world" in result
    assert "*" not in result


# ---------------------------------------------------------------------------
# BUG-05 – cp1252 / encoding cascade
# ---------------------------------------------------------------------------

def test_bug05_extract_text_from_md_reads_cp1252_file_without_crash():
    """BUG-05: extract_text_from_md must handle cp1252-encoded files (e.g.
    Windows-saved markdown with smart quotes / em-dashes) without raising
    UnicodeDecodeError.  Previously the function crashed on non-UTF-8 input.
    """
    # U+201C / U+201D are the proper Unicode smart-quotes that map to cp1252
    # bytes 0x93 / 0x94.  Bare \x93 in a Python 3 str is U+0093, a C1 control
    # character that cp1252 cannot encode — use the correct codepoints instead.
    cp1252_content = (
        "Product “overview” – build volume 300×300×300 mm"
    )

    with tempfile.NamedTemporaryFile(
        suffix=".md", delete=False, mode="wb"
    ) as tmp:
        tmp.write(cp1252_content.encode("cp1252"))
        tmp_path = tmp.name

    try:
        result = extract_text_from_md(tmp_path)
        # Must return a non-empty string, not an error marker
        assert result
        assert not result.startswith("[ПОМИЛКА]"), (
            f"extract_text_from_md returned an error for cp1252 file: {result}"
        )
        # The round-tripped content must include readable ASCII parts
        assert "overview" in result or "Product" in result
    finally:
        os.unlink(tmp_path)


def test_bug05_extract_text_from_md_handles_missing_file_gracefully():
    """BUG-05 (related): extract_text_from_md should return an error string,
    not raise, when the file does not exist.
    """
    result = extract_text_from_md("/nonexistent/path/file.md")
    assert result.startswith("[ПОМИЛКА]")


# ---------------------------------------------------------------------------
# BUG-01 – Gemini delete_file called even after generate_content raises
# ---------------------------------------------------------------------------

def test_bug01_extract_pdf_with_gemini_deletes_file_on_generate_content_error():
    """BUG-01: _extract_pdf_with_gemini must call genai.delete_file in the
    finally block even when generate_content raises an exception.  Previously
    the uploaded file was leaked whenever the model call failed.
    """
    fake_uploaded = MagicMock()
    fake_uploaded.name = "files/test-upload-123"

    fake_genai = MagicMock()
    fake_genai.upload_file.return_value = fake_uploaded
    fake_genai.types.GenerationConfig = MagicMock(return_value={})

    fake_model = MagicMock()
    fake_model.generate_content.side_effect = RuntimeError("Gemini API error")
    fake_genai.GenerativeModel.return_value = fake_model

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        patch("content_generator.tools.parsers.genai", fake_genai, create=True),
        tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp,
    ):
        tmp_path = tmp.name

    try:
        with pytest.raises(RuntimeError, match="Gemini API error"):
            # We patch 'google.generativeai' inside the function via lazy import
            with patch.dict(
                "sys.modules",
                {"google.generativeai": fake_genai},
            ):
                _extract_pdf_with_gemini(tmp_path)

        # delete_file MUST have been called despite the exception
        fake_genai.delete_file.assert_called_once_with(fake_uploaded.name)
    finally:
        os.unlink(tmp_path)


def test_bug01_extract_pdf_with_gemini_deletes_file_on_successful_run():
    """BUG-01 (positive case): delete_file is also called on success."""
    fake_uploaded = MagicMock()
    fake_uploaded.name = "files/ok-upload"

    fake_candidate = MagicMock()
    fake_candidate.finish_reason.name = "STOP"

    fake_response = MagicMock()
    fake_response.candidates = [fake_candidate]
    fake_response.text = "Extracted text " * 20  # > MIN_PDF_TEXT_LENGTH

    fake_genai = MagicMock()
    fake_genai.upload_file.return_value = fake_uploaded
    fake_genai.GenerativeModel.return_value.generate_content.return_value = fake_response
    fake_genai.types.GenerationConfig = MagicMock(return_value={})

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp,
    ):
        tmp_path = tmp.name

    try:
        with patch.dict("sys.modules", {"google.generativeai": fake_genai}):
            result = _extract_pdf_with_gemini(tmp_path)

        assert "Extracted text" in result
        fake_genai.delete_file.assert_called_once_with(fake_uploaded.name)
    finally:
        os.unlink(tmp_path)
