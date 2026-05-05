"""Unit tests for Pydantic schemas and config loader in content_generator.crew.

Each test guards against a specific regression.  No API calls — schemas are
pure Pydantic validation; _load_yaml_config uses only the filesystem.
"""

import tempfile
import os

import pytest
from pydantic import ValidationError

from content_generator.crew import (
    TechSpecsOutput,
    QAVerdict,
    SupportData,
    _load_yaml_config,
)


# ---------------------------------------------------------------------------
# BUG-08 – TechSpecsOutput accepts missing Support_Data
# ---------------------------------------------------------------------------

class TestTechSpecsOutputSupportData:

    VALID_KEY_FEATURES = [
        {"feature_name": "Speed", "spec_value": "600 mm/s", "benefit": "Prints fast"},
        {"feature_name": "Volume", "spec_value": "300×300 mm", "benefit": "Large parts"},
        {"feature_name": "Temp", "spec_value": "300 °C", "benefit": "Exotic filaments"},
    ]
    VALID_SPECS = {"Printing": {"Speed": "600 mm/s"}}

    def test_bug08_missing_support_data_does_not_raise_validation_error(self):
        """BUG-08: TechSpecsOutput must not raise ValidationError when
        Support_Data is omitted — it has default_factory=SupportData.
        Previously the field lacked a default and always required a value.
        """
        model = TechSpecsOutput(
            Technical_Specifications=self.VALID_SPECS,
            Key_Features=self.VALID_KEY_FEATURES,
            Marketing_Content="Great product with amazing specs.",
        )
        assert isinstance(model.Support_Data, SupportData)

    def test_bug08_default_support_data_has_empty_lists(self):
        """BUG-08: The default SupportData must have empty faqs and troubleshooting."""
        model = TechSpecsOutput(
            Technical_Specifications=self.VALID_SPECS,
            Key_Features=self.VALID_KEY_FEATURES,
            Marketing_Content="Marketing text.",
        )
        assert model.Support_Data.faqs == []
        assert model.Support_Data.troubleshooting == []

    def test_bug08_explicit_support_data_is_preserved(self):
        """BUG-08: When Support_Data is explicitly supplied it must be kept."""
        support = {"faqs": [{"Question": "Q?", "Answer": "A."}], "troubleshooting": []}
        model = TechSpecsOutput(
            Technical_Specifications=self.VALID_SPECS,
            Key_Features=self.VALID_KEY_FEATURES,
            Marketing_Content="Marketing text.",
            Support_Data=support,
        )
        assert len(model.Support_Data.faqs) == 1
        assert model.Support_Data.faqs[0]["Question"] == "Q?"


# ---------------------------------------------------------------------------
# BUG-07 – normalize_spec_values handles scalar, list, and None without crash
# ---------------------------------------------------------------------------

class TestNormalizeSpecValues:

    VALID_FEATURES = [
        {"feature_name": "F1", "spec_value": "v1", "benefit": "b1"},
        {"feature_name": "F2", "spec_value": "v2", "benefit": "b2"},
        {"feature_name": "F3", "spec_value": "v3", "benefit": "b3"},
    ]

    def _make(self, specs):
        return TechSpecsOutput(
            Technical_Specifications=specs,
            Key_Features=self.VALID_FEATURES,
            Marketing_Content="Text.",
        )

    def test_bug07_scalar_string_category_wraps_in_dict(self):
        """BUG-07: A category whose value is a plain string (not a dict)
        must be wrapped into {'value': <string>} rather than crashing.
        Previously the code did not handle this path and raised TypeError.
        """
        model = self._make({"Printing": "600 mm/s"})
        assert model.Technical_Specifications["Printing"] == {"value": "600 mm/s"}

    def test_bug07_list_category_joins_to_comma_string(self):
        """BUG-07: A category whose value is a list must be joined with ', '
        rather than crashing. Previously list categories caused AttributeError.
        """
        model = self._make({"Colors": ["Red", "Blue", "Green"]})
        assert model.Technical_Specifications["Colors"] == {"value": "Red, Blue, Green"}

    def test_bug07_none_category_gives_empty_dict(self):
        """BUG-07: A category whose value is None must become {} (empty dict).
        Previously None caused a crash inside str(fields) comparisons.
        """
        model = self._make({"OptionalSpec": None})
        assert model.Technical_Specifications["OptionalSpec"] == {}

    def test_bug07_nested_list_values_within_dict_are_joined(self):
        """BUG-07: A nested dict where a key has a list value must join it.
        E.g., {"Cat": {"key": ["a", "b"]}} → {"Cat": {"key": "a, b"}}.
        """
        model = self._make({"Printing": {"Profiles": ["Draft", "Standard", "Fine"]}})
        assert model.Technical_Specifications["Printing"]["Profiles"] == "Draft, Standard, Fine"

    def test_bug07_normal_nested_dict_passes_through_unchanged(self):
        """BUG-07: Normal nested dict specs must pass through without mutation."""
        model = self._make({"Printing": {"Speed": "600 mm/s", "Temp": "300 °C"}})
        assert model.Technical_Specifications["Printing"]["Speed"] == "600 mm/s"
        assert model.Technical_Specifications["Printing"]["Temp"] == "300 °C"


# ---------------------------------------------------------------------------
# BUG-11 – QAVerdict rejects APPROVED+score<80, accepts APPROVED+score>=80
# ---------------------------------------------------------------------------

class TestQAVerdictConsistency:

    BASE = dict(
        fact_errors=[],
        external_links_found=[],
        missing_sections=[],
        expert_insight_present=True,
        technical_tip_present=True,
    )

    def test_bug11_approved_with_score_below_80_raises_validation_error(self):
        """BUG-11: APPROVED + uniqueness_score < 80.0 must raise ValidationError
        to prevent contradictory verdicts from reaching downstream tasks.
        Previously the model_validator was absent and any score was accepted.
        """
        with pytest.raises(ValidationError) as exc_info:
            QAVerdict(status="APPROVED", uniqueness_score=79.9, **self.BASE)
        assert "80" in str(exc_info.value) or "uniqueness" in str(exc_info.value).lower()

    def test_bug11_approved_with_score_at_exactly_80_is_valid(self):
        """BUG-11: APPROVED + uniqueness_score == 80.0 must NOT raise.
        The boundary is inclusive: >= 80.0 is allowed.
        """
        verdict = QAVerdict(status="APPROVED", uniqueness_score=80.0, **self.BASE)
        assert verdict.status == "APPROVED"
        assert verdict.uniqueness_score == 80.0

    def test_bug11_approved_with_score_above_80_is_valid(self):
        """BUG-11: APPROVED + uniqueness_score > 80.0 is always valid."""
        verdict = QAVerdict(status="APPROVED", uniqueness_score=95.5, **self.BASE)
        assert verdict.status == "APPROVED"

    def test_bug11_rejected_with_any_score_is_valid(self):
        """BUG-11: REJECTED status has no score constraint — any score is valid."""
        verdict = QAVerdict(status="REJECTED", uniqueness_score=0.0, **self.BASE)
        assert verdict.status == "REJECTED"

    def test_bug11_approved_with_score_zero_raises(self):
        """BUG-11: The extreme case APPROVED + score=0 must also be rejected."""
        with pytest.raises(ValidationError):
            QAVerdict(status="APPROVED", uniqueness_score=0.0, **self.BASE)


# ---------------------------------------------------------------------------
# BUG-06 – _load_yaml_config raises FileNotFoundError with helpful message
# ---------------------------------------------------------------------------

class TestLoadYamlConfig:

    def test_bug06_missing_file_raises_file_not_found_error(self):
        """BUG-06: _load_yaml_config must raise FileNotFoundError (not a
        generic OSError or silent None) when the config file does not exist.
        The original code let Python's built-in error bubble with no context.
        """
        with pytest.raises(FileNotFoundError):
            _load_yaml_config("/nonexistent/path/to/config.yaml")

    def test_bug06_error_message_contains_path(self):
        """BUG-06: The error message must include the missing path so the
        operator knows exactly which file to check.
        """
        missing = "/fake/config/agents.yaml"
        with pytest.raises(FileNotFoundError, match="agents.yaml"):
            _load_yaml_config(missing)

    def test_bug06_error_message_contains_helpful_hint(self):
        """BUG-06: The error message should contain a hint about the config/
        directory so operators understand where to look.
        """
        missing = "/fake/some_path/config.yaml"
        with pytest.raises(FileNotFoundError) as exc_info:
            _load_yaml_config(missing)
        msg = str(exc_info.value)
        assert "config" in msg.lower() or "directory" in msg.lower()

    def test_bug06_valid_yaml_file_loads_correctly(self, tmp_path):
        """BUG-06 (positive): A valid YAML mapping file must load without error."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("key: value\nnested:\n  a: 1\n", encoding="utf-8")
        result = _load_yaml_config(str(yaml_file))
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_bug06_non_dict_yaml_raises_value_error(self, tmp_path):
        """BUG-06: A YAML file that parses to a non-dict (e.g. a list) must
        raise ValueError, not silently return the wrong type.
        """
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapping"):
            _load_yaml_config(str(yaml_file))
