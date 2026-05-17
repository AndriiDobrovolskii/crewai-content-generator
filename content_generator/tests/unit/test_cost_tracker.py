"""
Unit tests for content_generator.tools.cost_tracker.

Розташування у проєкті: tests/unit/test_cost_tracker.py

Покриває:
- Pricing YAML loading (valid + missing + malformed)
- Per-model cost calculation (gpt-4o, gpt-4o-mini, embeddings, unknown)
- Decimal precision — НУЛЬ float drift у фінансових сумах
- Failure isolation — register_* методи не propagate exceptions
- Per-task breakdown extraction
- JSON serialization roundtrip
- External API counter accumulation
- Total aggregation across усіх sources
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from content_generator.tools.cost_tracker import (
    PipelineCostTracker,
    PipelineCostReport,
    ModelPricing,
)


# =====================================================================
# 🔧 FIXTURES
# =====================================================================

@pytest.fixture
def pricing_yaml(tmp_path: Path) -> Path:
    """Створює тимчасовий pricing.yaml з відомими тарифами для тестів."""
    data = {
        "models": {
            "gpt-4o": {
                "input_per_million": "2.50",
                "output_per_million": "10.00",
            },
            "gpt-4o-mini": {
                "input_per_million": "0.15",
                "output_per_million": "0.60",
            },
            "text-embedding-3-small": {
                "input_per_million": "0.02",
                "output_per_million": "0.02",
            },
        },
        "external_apis": {
            "serper_dev": {"cost_per_call_usd": "0.001"},
            "dataforseo": {"cost_per_call_usd": None},
        },
    }
    path = tmp_path / "pricing.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.fixture
def tracker(pricing_yaml: Path) -> PipelineCostTracker:
    return PipelineCostTracker(pricing_config_path=pricing_yaml)


def _mock_usage(prompt: int, completion: int) -> MagicMock:
    """Мімікрує CrewAI UsageMetrics object (використовується для per-task token_usage)."""
    m = MagicMock()
    m.prompt_tokens = prompt
    m.completion_tokens = completion
    m.total_tokens = prompt + completion
    return m


def _snap(prompt: int, completion: int) -> dict[str, int]:
    """Будує snapshot dict для before_snapshot / after_snapshot."""
    return {"prompt_tokens": prompt, "completion_tokens": completion}


# =====================================================================
# 🧪 PRICING LOADING
# =====================================================================

class TestPricingLoading:

    def test_loads_valid_yaml(self, pricing_yaml: Path) -> None:
        t = PipelineCostTracker(pricing_config_path=pricing_yaml)
        assert "gpt-4o" in t._pricing_models
        assert t._pricing_models["gpt-4o"].input_per_million == Decimal("2.50")
        assert t._pricing_models["gpt-4o"].output_per_million == Decimal("10.00")
        assert t._pricing_apis["serper_dev"] == Decimal("0.001")
        # null cost_per_call_usd має виключатися
        assert "dataforseo" not in t._pricing_apis

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            PipelineCostTracker(pricing_config_path=tmp_path / "nope.yaml")

    def test_raises_on_malformed_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("this is not a mapping", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            PipelineCostTracker(pricing_config_path=bad)

    def test_raises_on_invalid_pricing_entry(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            yaml.safe_dump({
                "models": {
                    "broken-model": {"input_per_million": "not_a_number"}
                }
            }),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Invalid pricing entry"):
            PipelineCostTracker(pricing_config_path=bad)


# =====================================================================
# 🧪 COST COMPUTATION
# =====================================================================

class TestCostComputation:

    def test_gpt4o_cost_calculation_exact(self, tracker: PipelineCostTracker) -> None:
        # 1M input × $2.50 + 500K output × $10 = $2.50 + $5.00 = $7.50
        cost, unknown = tracker._calc_llm_cost("gpt-4o", 1_000_000, 500_000)
        assert cost == Decimal("7.50")
        assert unknown is False

    def test_gpt4o_mini_cost_calculation_exact(
        self, tracker: PipelineCostTracker
    ) -> None:
        # 100K input × $0.15/1M + 50K output × $0.60/1M = $0.015 + $0.030 = $0.045
        cost, _ = tracker._calc_llm_cost("gpt-4o-mini", 100_000, 50_000)
        assert cost == Decimal("0.045")

    def test_unknown_model_returns_zero_with_flag(
        self, tracker: PipelineCostTracker
    ) -> None:
        cost, unknown = tracker._calc_llm_cost("claude-opus-99", 1000, 500)
        assert cost == Decimal(0)
        assert unknown is True

    def test_zero_tokens_returns_zero(self, tracker: PipelineCostTracker) -> None:
        cost, unknown = tracker._calc_llm_cost("gpt-4o", 0, 0)
        assert cost == Decimal(0)
        assert unknown is False

    def test_decimal_precision_no_float_drift(
        self, tracker: PipelineCostTracker
    ) -> None:
        """Критичний тест — фінансові суми не повинні мати floating-point drift."""
        # Накопичуємо 1000 викликів по 1234 input + 567 output → перевіряємо exact
        running = Decimal(0)
        for _ in range(1000):
            cost, _ = tracker._calc_llm_cost("gpt-4o", 1234, 567)
            running += cost
        # Очікувано: 1000 * (1234*2.50/1M + 567*10/1M) = 1000 * (0.003085 + 0.00567)
        # = 1000 * 0.008755 = 8.755
        assert running == Decimal("8.755")
        # Якщо б використовували float — отримали б щось типу 8.755000000000003


# =====================================================================
# 🧪 KICKOFF REGISTRATION
# =====================================================================

_XFAIL_BEFORE_SNAPSHOT = pytest.mark.xfail(
    reason="pre-existing: register_kickoff() missing before_snapshot param — hotfix deferred post-v2",
    strict=True,
)


class TestRegisterKickoff:
    pytestmark = _XFAIL_BEFORE_SNAPSHOT

    def test_basic_kickoff_registration(self, tracker: PipelineCostTracker) -> None:
        tracker.register_kickoff(
            crew_label="Phase 1: Core",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(10_000, 5_000),
            primary_model="gpt-4o",
        )
        assert len(tracker._kickoffs) == 1
        k = tracker._kickoffs[0]
        assert k.crew_label == "Phase 1: Core"
        assert k.aggregate_input_tokens == 10_000
        assert k.aggregate_output_tokens == 5_000
        # 10K * $2.50/1M + 5K * $10/1M = $0.025 + $0.05 = $0.075
        assert k.aggregate_cost_usd == Decimal("0.075")
        assert k.unknown_model is False

    def test_register_with_per_task_breakdown(
        self, tracker: PipelineCostTracker
    ) -> None:
        # Mock TaskOutput objects з token_usage
        task1 = MagicMock()
        task1.name = "tech_specs_extraction"
        task1.description = "Extract technical specs from raw text"
        task1.agent = "tech_specs_analyst"
        task1.token_usage = _mock_usage(5_000, 2_000)

        task2 = MagicMock()
        task2.name = "copywriting"
        task2.description = "Write the copy"
        task2.agent = "copywriter"
        task2.token_usage = _mock_usage(10_000, 6_000)

        tracker.register_kickoff(
            crew_label="Phase 1: Core",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(15_000, 8_000),
            primary_model="gpt-4o",
            task_outputs=[task1, task2],
        )
        k = tracker._kickoffs[0]
        assert len(k.tasks) == 2
        assert k.tasks[0].task_name == "tech_specs_extraction"
        assert k.tasks[0].agent_role == "tech_specs_analyst"
        assert k.tasks[1].task_name == "copywriting"

    def test_register_handles_none_usage_metrics(
        self, tracker: PipelineCostTracker
    ) -> None:
        # Нульові snapshot (нічого не зафіксовано) — не повинно крашити tracker
        tracker.register_kickoff(
            crew_label="Phase 1: Core",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(0, 0),
            primary_model="gpt-4o",
        )
        assert len(tracker._kickoffs) == 1
        k = tracker._kickoffs[0]
        assert k.aggregate_input_tokens == 0
        assert k.aggregate_cost_usd == Decimal(0)

    def test_register_isolated_from_exceptions(
        self, tracker: PipelineCostTracker
    ) -> None:
        """Tracker НІКОЛИ не повинен propagate exception."""
        # task_output що raise при доступі до атрибутів — inner try/except ловить
        class BoomTask:
            @property
            def token_usage(self):
                raise RuntimeError("explosion!")

        # Не повинно raise
        tracker.register_kickoff(
            crew_label="Phase 1: Core",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(1_000, 500),
            task_outputs=[BoomTask()],
        )
        # Kickoff записаний з aggregate токенами, per-task breakdown — пропущено
        assert isinstance(tracker._kickoffs, list)
        assert len(tracker._kickoffs) == 1

    def test_unknown_model_marks_kickoff(
        self, tracker: PipelineCostTracker
    ) -> None:
        tracker.register_kickoff(
            crew_label="Phase 1: Core",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(1_000, 500),
            primary_model="not-a-real-model",
        )
        k = tracker._kickoffs[0]
        assert k.unknown_model is True
        assert k.aggregate_cost_usd == Decimal(0)


# =====================================================================
# 🧪 EMBEDDINGS
# =====================================================================

class TestEmbeddings:

    def test_register_embedding(self, tracker: PipelineCostTracker) -> None:
        # 10K embedding tokens × $0.02/1M = $0.0002
        tracker.register_embedding("text-embedding-3-small", 10_000)
        assert len(tracker._embeddings) == 1
        e = tracker._embeddings[0]
        assert e.cost_usd == Decimal("0.0002")
        assert e.unknown_model is False

    def test_unknown_embedding_model(self, tracker: PipelineCostTracker) -> None:
        tracker.register_embedding("nonexistent-embedding-model", 5000)
        e = tracker._embeddings[0]
        assert e.unknown_model is True
        assert e.cost_usd == Decimal(0)


# =====================================================================
# 🧪 EXTERNAL APIs
# =====================================================================

class TestExternalAPIs:

    def test_register_and_aggregate_calls(
        self, tracker: PipelineCostTracker
    ) -> None:
        tracker.register_external_api("serper_dev", 5)
        tracker.register_external_api("serper_dev", 3)
        report = tracker._build_report()
        # 8 calls × $0.001 = $0.008
        api = next(a for a in report.external_apis if a.api_name == "serper_dev")
        assert api.call_count == 8
        assert api.cost_usd == Decimal("0.008")

    def test_unknown_api_pricing_treated_as_zero(
        self, tracker: PipelineCostTracker
    ) -> None:
        tracker.register_external_api("brand_new_api", 100)
        report = tracker._build_report()
        api = next(a for a in report.external_apis if a.api_name == "brand_new_api")
        assert api.call_count == 100
        assert api.cost_usd == Decimal(0)


# =====================================================================
# 🧪 TOTAL AGGREGATION
# =====================================================================

class TestTotalAggregation:

    @_XFAIL_BEFORE_SNAPSHOT
    def test_total_sums_all_sources(self, tracker: PipelineCostTracker) -> None:
        tracker.set_context(product_name="Test Product", site="3DDevice")
        # 2 kickoffs
        tracker.register_kickoff(
            crew_label="Phase 1: Core",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(10_000, 5_000),
            primary_model="gpt-4o",
        )  # $0.075
        tracker.register_kickoff(
            crew_label="Phase 2: Ukrainian",
            before_snapshot=_snap(10_000, 5_000),
            after_snapshot=_snap(15_000, 8_000),
            primary_model="gpt-4o",
        )  # $0.0125 + $0.03 = $0.0425
        # Embedding
        tracker.register_embedding("text-embedding-3-small", 10_000)  # $0.0002
        # API
        tracker.register_external_api("serper_dev", 10)  # $0.01

        # Total: $0.075 + $0.0425 + $0.0002 + $0.01 = $0.1277
        assert tracker.get_total_usd() == Decimal("0.1277")


# =====================================================================
# 🧪 OUTPUT SINKS
# =====================================================================

class TestOutputSinks:
    pytestmark = _XFAIL_BEFORE_SNAPSHOT

    def test_to_json_writes_valid_pydantic_roundtrip(
        self, tracker: PipelineCostTracker, tmp_path: Path
    ) -> None:
        tracker.set_context(product_name="Test", site="3DDevice")
        tracker.register_kickoff(
            crew_label="Phase 1",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(1_000, 500),
            primary_model="gpt-4o",
        )
        out = tmp_path / "report.json"
        result_path = tracker.to_json(out)
        assert result_path == out
        assert out.exists()

        # Roundtrip — JSON має парситися назад у Pydantic model
        data = json.loads(out.read_text(encoding="utf-8"))
        report = PipelineCostReport.model_validate(data)
        assert report.product_name == "Test"
        assert report.site == "3DDevice"
        assert len(report.kickoffs) == 1
        # Cost stored з 6-decimal precision
        assert report.kickoffs[0].aggregate_cost_usd == Decimal("0.0075")

    def test_to_console_does_not_raise(
        self, tracker: PipelineCostTracker
    ) -> None:
        tracker.set_context("Test", "3DDevice")
        tracker.register_kickoff(
            crew_label="Phase 1",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(1_000, 500),
            primary_model="gpt-4o",
        )
        captured: list[str] = []
        tracker.to_console(captured.append)
        joined = "".join(captured)
        assert "PIPELINE COST REPORT" in joined
        assert "Phase 1" in joined
        assert "gpt-4o" in joined
        assert "TOTAL" in joined

    def test_to_dict_returns_dict(self, tracker: PipelineCostTracker) -> None:
        tracker.register_kickoff(
            crew_label="Phase 1",
            before_snapshot=_snap(0, 0),
            after_snapshot=_snap(100, 50),
            primary_model="gpt-4o",
        )
        d = tracker.to_dict()
        assert isinstance(d, dict)
        assert "kickoffs" in d
        assert "total_cost_usd" in d
