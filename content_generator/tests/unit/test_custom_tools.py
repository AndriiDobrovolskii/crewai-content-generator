"""Unit tests for content_generator.tools.custom_tools.

Each test guards against a specific regression.  No real API calls.
"""

import difflib
from unittest.mock import MagicMock, patch

import pytest

from content_generator.tools.custom_tools import (
    ContentSimilarityTool,
    USMeasurementCalculatorTool,
)


# ---------------------------------------------------------------------------
# BUG-13 – _format_number clean output (no float repr artifacts)
# ---------------------------------------------------------------------------

class TestFormatNumber:
    """Tests for USMeasurementCalculatorTool._format_number."""

    def setup_method(self):
        self.tool = USMeasurementCalculatorTool()

    def test_bug13_format_number_integer_float_returns_no_decimal(self):
        """BUG-13: _format_number(11.0) must return '11', not '11.0' or '11.00'.
        Previously f-string without rstrip gave '11.0' which is not clean output.
        """
        assert self.tool._format_number(11.0) == "11"

    def test_bug13_format_number_two_decimal_places_unchanged(self):
        """BUG-13: _format_number(7.87) must return '7.87', preserving
        meaningful decimals without adding trailing zeros.
        """
        assert self.tool._format_number(7.87) == "7.87"

    def test_bug13_format_number_no_repr_artifacts_from_float_arithmetic(self):
        """BUG-13: 300 / 25.4 = 11.811023... → round to 2dp = 11.81.
        The old f"{val}" could emit '11.810000000000002'-style repr.
        """
        val = round(300 / 25.4, 2)  # = 11.81
        result = self.tool._format_number(val)
        assert result == "11.81"
        assert "000" not in result, "Float repr artifact detected"

    def test_bug13_format_number_zero_gives_zero(self):
        """BUG-13: _format_number(0.0) must return '0'."""
        assert self.tool._format_number(0.0) == "0"

    def test_bug13_format_number_trailing_zero_stripped(self):
        """BUG-13: _format_number(10.50) must return '10.5', not '10.50'."""
        assert self.tool._format_number(10.50) == "10.5"


# ---------------------------------------------------------------------------
# BUG-14 – Missing 'value' field returns error string, not 0 or crash
# ---------------------------------------------------------------------------

class TestUSMeasurementCalculatorMissingValue:
    """Tests for USMeasurementCalculatorTool handling of missing 'value'."""

    def setup_method(self):
        self.tool = USMeasurementCalculatorTool()

    def test_bug14_missing_value_returns_error_string(self):
        """BUG-14: When a dict item lacks 'value', _run must return an error
        string describing the missing field.  Previously the code crashed with
        AttributeError or returned '0' which is a silent wrong answer.
        """
        result = self.tool._run([{"unit": "mm", "label": "Width"}])
        assert isinstance(result, str)
        assert "Error" in result or "error" in result.lower()
        assert result != "0"
        assert result.strip() != ""

    def test_bug14_missing_value_mentions_label_in_error(self):
        """BUG-14: The error string should include the label so the caller
        can identify which field was problematic.
        """
        result = self.tool._run([{"unit": "kg", "label": "WeightField"}])
        assert "WeightField" in result

    def test_bug14_missing_value_does_not_raise(self):
        """BUG-14: Missing 'value' must not propagate an exception.
        The tool should gracefully produce an error string.
        """
        try:
            self.tool._run([{"unit": "mm"}])
        except Exception as exc:
            pytest.fail(f"_run raised unexpectedly: {exc}")

    def test_bug14_valid_conversion_still_works_alongside_missing(self):
        """BUG-14: A batch with one missing-value item and one valid item
        must produce two lines — error for the bad one, result for the good.
        """
        result = self.tool._run([
            {"unit": "mm", "label": "Missing"},           # no 'value'
            {"value": 300, "unit": "mm", "label": "Width"},  # valid
        ])
        lines = result.strip().splitlines()
        assert len(lines) == 2
        assert "Error" in lines[0] or "error" in lines[0].lower()
        assert "Width" in lines[1]
        assert '"' in lines[1]  # inches symbol present


# ---------------------------------------------------------------------------
# BUG-15 – ContentSimilarityTool boundary: PASSED at exactly 80.0%
# ---------------------------------------------------------------------------

class TestContentSimilarityBoundary:
    """Tests for the 80% uniqueness boundary in ContentSimilarityTool._run."""

    def setup_method(self):
        self.tool = ContentSimilarityTool()

    def _long_text(self, words):
        """Build a text long enough to pass MIN_TEXT_LENGTH (50 chars)."""
        return " ".join(words) + " " * 10  # pad to ensure len > 50

    def test_bug15_returns_passed_at_exactly_80_percent_uniqueness(self, mocker):
        """BUG-15: At uniqueness == 80.0% (boundary), the result must start
        with 'PASSED'.  A strict '<' check means 80.0 is not rejected;
        the bug was using '<=' which incorrectly failed at exactly 80.0.
        """
        # Force ratio = 0.2  →  uniqueness = (1-0.2)*100 = 80.0
        mock_sm = MagicMock()
        mock_sm.ratio.return_value = 0.2
        mocker.patch(
            "content_generator.tools.custom_tools.difflib.SequenceMatcher",
            return_value=mock_sm,
        )
        # Use completely different word sets so n-gram overlap is 0 (no WARNING)
        source = self._long_text(["alpha", "beta", "gamma", "delta", "epsilon"] * 5)
        generated = self._long_text(["one", "two", "three", "four", "five"] * 5)

        result = self.tool._run(source, generated)
        assert result.startswith("PASSED"), (
            f"Expected PASSED at exactly 80.0% uniqueness, got: {result!r}"
        )

    def test_bug15_returns_failed_below_80_percent(self, mocker):
        """BUG-15 (complement): At uniqueness < 80.0% the result must be FAILED."""
        # ratio = 0.201  →  uniqueness = (1-0.201)*100 = 79.9%
        mock_sm = MagicMock()
        mock_sm.ratio.return_value = 0.201
        mocker.patch(
            "content_generator.tools.custom_tools.difflib.SequenceMatcher",
            return_value=mock_sm,
        )
        source = self._long_text(["alpha", "beta", "gamma"] * 10)
        generated = self._long_text(["one", "two", "three"] * 10)

        result = self.tool._run(source, generated)
        assert result.startswith("FAILED"), (
            f"Expected FAILED below 80.0% uniqueness, got: {result!r}"
        )

    def test_bug15_non_empty_result_for_any_valid_inputs(self):
        """BUG-15 (smoke): The tool must return a non-empty string for any
        valid text pair without raising.  Whether the result is PASSED, FAILED
        or WARNING depends on content; this test only guards against crashes.
        """
        source = "word1 word2 word3 specification data " * 15
        generated = "item1 item2 item3 description text " * 15
        result = self.tool._run(source, generated)
        assert isinstance(result, str)
        assert result.strip() != ""

    def test_bug15_identical_text_fails(self):
        """BUG-15 (smoke): Identical texts must always return FAILED."""
        text = ("The printer features a 300×300×300 mm build volume. " * 5).strip()
        result = self.tool._run(text, text)
        assert result.startswith("FAILED"), (
            f"Identical texts should be FAILED, got: {result!r}"
        )
