"""
Pipeline Cost Tracker — Per-kickoff and per-task USD attribution for CrewAI runs.

Розташування у проєкті: src/content_generator/tools/cost_tracker.py

Інстанціюється РАЗ на pipeline run. Кожен виклик `register_kickoff()` фіксує
token usage з CrewAI Crew, множить на per-model pricing з config/pricing.yaml,
і агрегує у структурований PipelineCostReport.

Архітектурні інваріанти:
- Decimal-арифметика тільки — жодного floating-point дрейфу у фінансових сумах.
- Failure-isolated: кожен `register_*` метод обгорнутий у try/except —
  баг trecker'а НІКОЛИ не вбиває pipeline. Pipeline без метрик — degraded
  but operational. Pipeline що падає через telemetry — недопустимо.
- Невідома модель → log warning + cost_usd=0 + unknown_model=True flag.
  Тиха нуль-атрибуція — anti-pattern.
- Pricing externalized у YAML — оновлення тарифів не потребує зміни коду.

Public API:
    tracker = PipelineCostTracker()
    tracker.set_context(product_name="Bambu A1 Mini", site="3DDevice")

    # Після кожного crew.kickoff()
    tracker.register_kickoff(
        crew_label="Phase 1: Core",
        usage_metrics=active_core_crew.usage_metrics,
        primary_model="gpt-4o",
        task_outputs=core_result.tasks_output,  # optional — per-task breakdown
    )

    # External API лічильники
    tracker.register_external_api("serper_dev", call_count=12)

    # Embeddings (memory=True kicks)
    tracker.register_embedding("text-embedding-3-small", tokens=4500)

    # Output
    tracker.to_console(print)
    tracker.to_json(Path("output/.../cost_report.json"))
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_serializer

logger = logging.getLogger(__name__)


# =====================================================================
# 📐 ОКРУГЛЕННЯ — STORAGE vs DISPLAY
# =====================================================================

DECIMAL_PRECISION = Decimal("0.000001")  # 6 знаків — зберігання
DISPLAY_PRECISION = Decimal("0.0001")    # 4 знаки — display


def _quantize_storage(value: Decimal) -> Decimal:
    """Округлення до storage precision (6 знаків, half-up)."""
    return value.quantize(DECIMAL_PRECISION, rounding=ROUND_HALF_UP)


def _quantize_display(value: Decimal) -> Decimal:
    """Округлення до display precision (4 знаки, half-up)."""
    return value.quantize(DISPLAY_PRECISION, rounding=ROUND_HALF_UP)


# =====================================================================
# 🛡️ PYDANTIC SCHEMAS (Hard Contracts)
# =====================================================================

class ModelPricing(BaseModel):
    """USD per 1,000,000 tokens. Decimal — never float."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    input_per_million: Decimal
    output_per_million: Decimal


class TaskCost(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_name: str
    agent_role: Optional[str] = None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    unknown_model: bool = False  # True якщо моделі немає у pricing.yaml

    @field_serializer('cost_usd')
    def _ser_cost(self, v: Decimal, _info) -> str:
        return str(_quantize_storage(v))


class KickoffCost(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    crew_label: str
    primary_model: str
    tasks: list[TaskCost] = Field(default_factory=list)
    aggregate_input_tokens: int
    aggregate_output_tokens: int
    aggregate_cost_usd: Decimal
    unknown_model: bool = False

    @field_serializer('aggregate_cost_usd')
    def _ser_cost(self, v: Decimal, _info) -> str:
        return str(_quantize_storage(v))


class EmbeddingCost(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str
    tokens: int
    cost_usd: Decimal
    unknown_model: bool = False

    @field_serializer('cost_usd')
    def _ser_cost(self, v: Decimal, _info) -> str:
        return str(_quantize_storage(v))


class ExternalAPICost(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_name: str
    call_count: int
    cost_usd: Decimal

    @field_serializer('cost_usd')
    def _ser_cost(self, v: Decimal, _info) -> str:
        return str(_quantize_storage(v))


class PipelineCostReport(BaseModel):
    """Top-level report emitted to JSON / console / Supabase."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    timestamp_utc: str
    product_name: str
    site: str
    kickoffs: list[KickoffCost]
    embeddings: list[EmbeddingCost]
    external_apis: list[ExternalAPICost]
    total_input_tokens: int
    total_output_tokens: int
    total_llm_cost_usd: Decimal
    total_embedding_cost_usd: Decimal
    total_external_api_cost_usd: Decimal
    total_cost_usd: Decimal

    @field_serializer(
        'total_llm_cost_usd',
        'total_embedding_cost_usd',
        'total_external_api_cost_usd',
        'total_cost_usd',
    )
    def _ser_cost(self, v: Decimal, _info) -> str:
        return str(_quantize_storage(v))


# =====================================================================
# 💰 PIPELINE COST TRACKER
# =====================================================================

class PipelineCostTracker:
    """
    Накопичує USD-вартості для одного pipeline run'у.

    Thread-unsafe — pipeline ECommerceContentCrew йде sequential,
    у одному потоці. Якщо в майбутньому pipeline стане multi-threaded —
    треба буде додати threading.Lock на _kickoffs / _embeddings / _external_apis.
    """

    def __init__(self, pricing_config_path: Path | str | None = None) -> None:
        self._pricing_models: dict[str, ModelPricing] = {}
        self._pricing_apis: dict[str, Decimal] = {}
        self._kickoffs: list[KickoffCost] = []
        self._embeddings: list[EmbeddingCost] = []
        self._external_apis: dict[str, int] = {}
        self._product_name: str = ""
        self._site: str = ""
        self._timestamp_utc: str = datetime.now(timezone.utc).isoformat()

        # Default pricing path: <project>/src/content_generator/config/pricing.yaml
        # (this file lives at <project>/src/content_generator/tools/cost_tracker.py,
        # so ../config/pricing.yaml is the canonical location)
        if pricing_config_path is None:
            pricing_config_path = (
                Path(__file__).resolve().parent.parent
                / "config"
                / "pricing.yaml"
            )
        self._load_pricing(Path(pricing_config_path))

    # ─────────────────────────────────────────────────────────────────
    # PRICING CONFIG LOADING
    # ─────────────────────────────────────────────────────────────────

    def _load_pricing(self, path: Path) -> None:
        """Завантажує pricing з YAML. Кидає на malformed/missing файли."""
        if not path.exists():
            raise FileNotFoundError(
                f"Pricing config not found at {path}. "
                f"Expected: <project>/src/content_generator/config/pricing.yaml"
            )

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(
                f"pricing.yaml must be a YAML mapping, got {type(data).__name__}"
            )

        # Models
        models_section = data.get("models") or {}
        for model_name, prices in models_section.items():
            try:
                self._pricing_models[model_name] = ModelPricing(
                    input_per_million=Decimal(str(prices["input_per_million"])),
                    output_per_million=Decimal(str(prices["output_per_million"])),
                )
            except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                raise ValueError(
                    f"Invalid pricing entry for model '{model_name}': {e}"
                ) from e

        # External APIs
        apis_section = data.get("external_apis") or {}
        for api_name, api_data in apis_section.items():
            cost = (api_data or {}).get("cost_per_call_usd")
            if cost is not None:
                try:
                    self._pricing_apis[api_name] = Decimal(str(cost))
                except (ValueError, TypeError, InvalidOperation) as e:
                    raise ValueError(
                        f"Invalid pricing entry for API '{api_name}': {e}"
                    ) from e

        logger.info(
            f"Cost tracker pricing loaded: "
            f"{len(self._pricing_models)} models, "
            f"{len(self._pricing_apis)} external APIs"
        )

    # ─────────────────────────────────────────────────────────────────
    # CONTEXT
    # ─────────────────────────────────────────────────────────────────

    def set_context(self, product_name: str, site: str) -> None:
        """Контекст для report header. Опційно, але рекомендовано."""
        self._product_name = product_name
        self._site = site

    # ─────────────────────────────────────────────────────────────────
    # CORE COST COMPUTATION
    # ─────────────────────────────────────────────────────────────────

    def _calc_llm_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> tuple[Decimal, bool]:
        """Повертає (cost_usd, unknown_model_flag)."""
        pricing = self._pricing_models.get(model)
        if pricing is None:
            logger.warning(
                f"Cost tracker: unknown model '{model}' — "
                f"recording $0 with unknown_model=True. "
                f"Add to pricing.yaml to enable cost tracking."
            )
            return Decimal(0), True

        # Cost = (tokens / 1_000_000) * price_per_million
        million = Decimal(1_000_000)
        input_cost = (Decimal(input_tokens) * pricing.input_per_million) / million
        output_cost = (Decimal(output_tokens) * pricing.output_per_million) / million
        return input_cost + output_cost, False

    @staticmethod
    def _safe_attr(obj: Any, name: str, default: int = 0) -> int:
        """Безпечне читання атрибуту — обробляє dict, object, None."""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return int(obj.get(name, default) or default)
        val = getattr(obj, name, default)
        try:
            return int(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def snapshot_llm(crew_obj: Any) -> dict[str, int]:
        """Знімає поточний стан _token_usage з усіх LLM в crew."""
        totals: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        for agent in getattr(crew_obj, "agents", []):
            llm = getattr(agent, "llm", None)
            if llm and hasattr(llm, "_token_usage"):
                totals["prompt_tokens"]    += llm._token_usage.get("prompt_tokens", 0)
                totals["completion_tokens"] += llm._token_usage.get("completion_tokens", 0)
        return totals

    # ─────────────────────────────────────────────────────────────────
    # REGISTRATION METHODS — усі failure-isolated
    # ─────────────────────────────────────────────────────────────────

    def register_kickoff(
        self,
        crew_label: str,
        before_snapshot: dict[str, int],
        after_snapshot: dict[str, int],
        primary_model: str = "gpt-4o",
        task_outputs: Optional[list] = None,
    ) -> None:
        """Реєструє один CrewAI kickoff. Failure-isolated."""
        try:
            input_t  = after_snapshot["prompt_tokens"]    - before_snapshot["prompt_tokens"]
            output_t = after_snapshot["completion_tokens"] - before_snapshot["completion_tokens"]

            agg_cost, unknown = self._calc_llm_cost(primary_model, input_t, output_t)

            tasks: list[TaskCost] = []
            if task_outputs:
                for to in task_outputs:
                    try:
                        t_usage = getattr(to, "token_usage", None)
                        if not t_usage:
                            continue

                        ti = self._safe_attr(t_usage, "prompt_tokens")
                        too = self._safe_attr(t_usage, "completion_tokens")

                        # Task name: name → description (truncated) → fallback
                        t_name = (
                            getattr(to, "name", None)
                            or (getattr(to, "description", "") or "")[:80].strip()
                            or "unknown_task"
                        )

                        # Agent role: може бути str або Agent object
                        agent_role = getattr(to, "agent", None)
                        if agent_role is not None and not isinstance(agent_role, str):
                            agent_role = (
                                getattr(agent_role, "role", None)
                                or str(agent_role)
                            )

                        t_cost, t_unknown = self._calc_llm_cost(primary_model, ti, too)

                        tasks.append(TaskCost(
                            task_name=t_name,
                            agent_role=agent_role,
                            model=primary_model,
                            input_tokens=ti,
                            output_tokens=too,
                            cost_usd=t_cost,
                            unknown_model=t_unknown,
                        ))
                    except Exception as task_exc:
                        logger.warning(
                            f"Cost tracker: per-task extraction failed: {task_exc}"
                        )

            self._kickoffs.append(KickoffCost(
                crew_label=crew_label,
                primary_model=primary_model,
                tasks=tasks,
                aggregate_input_tokens=input_t,
                aggregate_output_tokens=output_t,
                aggregate_cost_usd=agg_cost,
                unknown_model=unknown,
            ))
        except Exception as e:
            logger.exception(
                f"Cost tracker register_kickoff failed for '{crew_label}': {e}"
            )

    def register_embedding(self, model: str, tokens: int) -> None:
        """Реєструє embedding tokens (з CrewAI memory=True)."""
        try:
            cost, unknown = self._calc_llm_cost(model, tokens, 0)
            self._embeddings.append(EmbeddingCost(
                model=model,
                tokens=tokens,
                cost_usd=cost,
                unknown_model=unknown,
            ))
        except Exception as e:
            logger.warning(f"Cost tracker register_embedding failed: {e}")

    def register_external_api(self, api_name: str, call_count: int) -> None:
        """Інкрементує лічильник external API calls."""
        try:
            self._external_apis[api_name] = (
                self._external_apis.get(api_name, 0) + int(call_count)
            )
        except Exception as e:
            logger.warning(f"Cost tracker register_external_api failed: {e}")

    # ─────────────────────────────────────────────────────────────────
    # REPORT BUILDING
    # ─────────────────────────────────────────────────────────────────

    def _build_external_api_costs(self) -> list[ExternalAPICost]:
        out = []
        for api_name, count in self._external_apis.items():
            per_call = self._pricing_apis.get(api_name, Decimal(0))
            out.append(ExternalAPICost(
                api_name=api_name,
                call_count=count,
                cost_usd=per_call * Decimal(count),
            ))
        return out

    def _build_report(self) -> PipelineCostReport:
        external_costs = self._build_external_api_costs()

        total_input = sum(k.aggregate_input_tokens for k in self._kickoffs)
        total_output = sum(k.aggregate_output_tokens for k in self._kickoffs)
        total_llm = sum(
            (k.aggregate_cost_usd for k in self._kickoffs), Decimal(0)
        )
        total_embed = sum((e.cost_usd for e in self._embeddings), Decimal(0))
        total_api = sum((a.cost_usd for a in external_costs), Decimal(0))

        return PipelineCostReport(
            timestamp_utc=self._timestamp_utc,
            product_name=self._product_name,
            site=self._site,
            kickoffs=self._kickoffs,
            embeddings=self._embeddings,
            external_apis=external_costs,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_llm_cost_usd=total_llm,
            total_embedding_cost_usd=total_embed,
            total_external_api_cost_usd=total_api,
            total_cost_usd=total_llm + total_embed + total_api,
        )

    # ─────────────────────────────────────────────────────────────────
    # PUBLIC ACCESSORS
    # ─────────────────────────────────────────────────────────────────

    def get_total_usd(self) -> Decimal:
        """Швидкий доступ до total без повного report."""
        try:
            return self._build_report().total_cost_usd
        except Exception:
            return Decimal(0)

    def to_dict(self) -> dict:
        """Для майбутньої Supabase інтеграції (Stage 5)."""
        try:
            return self._build_report().model_dump(mode="json")
        except Exception as e:
            logger.exception(f"Cost tracker to_dict failed: {e}")
            return {}

    # ─────────────────────────────────────────────────────────────────
    # OUTPUT SINKS
    # ─────────────────────────────────────────────────────────────────

    def to_json(self, output_path: Path | str) -> Optional[Path]:
        """Записує report як JSON у вказаний шлях."""
        try:
            report = self._build_report()
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )
            return path
        except Exception as e:
            logger.exception(f"Cost tracker to_json failed: {e}")
            return None

    def to_console(self, log_callback: Callable[[str], None]) -> None:
        """Pretty multi-line printout через переданий callback (наприклад, _log)."""
        try:
            report = self._build_report()
            sep = "=" * 70
            log_callback(f"\n{sep}\n")
            log_callback(
                f"💰 PIPELINE COST REPORT  "
                f"({report.product_name or '?'} → {report.site or '?'})\n"
            )
            log_callback(f"{sep}\n")

            for k in report.kickoffs:
                cost_disp = _quantize_display(k.aggregate_cost_usd)
                tag = " [UNKNOWN_MODEL]" if k.unknown_model else ""
                log_callback(
                    f"  📦 {k.crew_label} ({k.primary_model}){tag}\n"
                    f"     Tokens: {k.aggregate_input_tokens:>9,} in /"
                    f" {k.aggregate_output_tokens:>9,} out"
                    f"   Cost: ${cost_disp}\n"
                )
                if k.tasks:
                    for t in k.tasks:
                        t_cost_disp = _quantize_display(t.cost_usd)
                        agent = f" ({t.agent_role})" if t.agent_role else ""
                        log_callback(
                            f"        ↳ {t.task_name}{agent}: "
                            f"{t.input_tokens:,}/{t.output_tokens:,}"
                            f" → ${t_cost_disp}\n"
                        )

            if report.embeddings:
                log_callback(f"\n  🧠 Embeddings:\n")
                for e in report.embeddings:
                    e_disp = _quantize_display(e.cost_usd)
                    log_callback(
                        f"     {e.model}: {e.tokens:,} tokens → ${e_disp}\n"
                    )

            if report.external_apis:
                log_callback(f"\n  🌐 External APIs:\n")
                for a in report.external_apis:
                    a_disp = _quantize_display(a.cost_usd)
                    log_callback(
                        f"     {a.api_name}: {a.call_count} calls → ${a_disp}\n"
                    )

            log_callback(f"\n  ─────────────────────────\n")
            log_callback(
                f"  Σ LLM completions:   "
                f"${_quantize_display(report.total_llm_cost_usd)}\n"
            )
            log_callback(
                f"  Σ Embeddings:        "
                f"${_quantize_display(report.total_embedding_cost_usd)}\n"
            )
            log_callback(
                f"  Σ External APIs:     "
                f"${_quantize_display(report.total_external_api_cost_usd)}\n"
            )
            log_callback(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            log_callback(
                f"  💰 TOTAL:            "
                f"${_quantize_display(report.total_cost_usd)}\n"
            )
            log_callback(f"{sep}\n\n")
        except Exception as e:
            logger.exception(f"Cost tracker to_console failed: {e}")
