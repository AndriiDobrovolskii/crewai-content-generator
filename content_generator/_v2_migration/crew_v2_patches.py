"""
crew_v2_patches.py
==================

Surgical patches to `src/content_generator/crew.py` for v2 architecture.

This file contains:
  1. NEW Pydantic schemas (ImageStoryboardItem, ImageStoryboard,
     SEOMetadataEntry, SEOMetadataBundle).
  2. Insert points in ECommerceContentCrew (new agent, new task,
     updated context chains).
  3. NEW SEOMetadataCrew class (small, post-pipeline).
  4. post_pipeline_hook orchestration function.

Each block is annotated with the EXACT location in crew.py where it
should be inserted (file regions are anchored to existing class/function
boundaries that already exist in your codebase).

USAGE:
  - Open `src/content_generator/crew.py`.
  - For each numbered block below, locate the anchor comment and apply
    the patch as instructed.
  - Run `uv run pytest tests/unit/test_crew_schemas.py -v` after each
    block to verify no regressions.
"""

# =====================================================================
# BLOCK 1 — NEW Pydantic schemas
# =====================================================================
# Anchor: ABOVE the existing `class QAVerdict(BaseModel):` declaration.
# Reason: schemas must be defined before they are referenced as
# output_pydantic on Task instances.
# =====================================================================

# >>> INSERT BLOCK 1 — START >>>
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class ImageStoryboardItem(BaseModel):
    """Один пункт сториборду — план для одного <img> у фінальному HTML."""

    url: str = Field(
        ...,
        description="Exact absolute URL of the image (must match Official_Images)."
    )
    alt_text: str = Field(
        ...,
        min_length=60,
        max_length=160,
        description="Screen-reader-friendly description of what is shown. "
                    "No keyword stuffing, no marketing adjectives. "
                    "Mentions product name + demonstrated capability."
    )
    lead_in_paragraph: str = Field(
        ...,
        min_length=20,
        description="1-3 sentence contextual paragraph inserted immediately "
                    "above the <img> in HTML. Must reference the image and "
                    "tie to the surrounding H2 anchor."
    )
    placement_anchor: str = Field(
        ...,
        description="Exact H2 text from the copywriter's draft where this "
                    "image is placed, OR the literal string 'HERO' for a "
                    "hero/overview shot placed between Quick Specs and the "
                    "first deep-dive H2."
    )
    loading_strategy: Literal["eager", "lazy"] = Field(
        ...,
        description="'eager' for the order=1 LCP candidate image only. "
                    "All other images MUST be 'lazy'."
    )
    order: int = Field(
        ...,
        ge=1,
        description="Global order index starting at 1. Determines render sequence."
    )


class ImageStoryboard(BaseModel):
    """Повний typed-контракт між image agent і frontend agent."""

    items: list[ImageStoryboardItem] = Field(
        default_factory=list,
        description="Ordered list of image storyboard items. Empty list is valid."
    )

    @model_validator(mode="after")
    def _validate_loading_invariants(self) -> "ImageStoryboard":
        """Інваріант LCP: рівно один eager image, і це item з найменшим order.

        Порожній список — валідний (немає зображень, frontend пропускає рендеринг).
        """
        if not self.items:
            return self

        eager_items = [i for i in self.items if i.loading_strategy == "eager"]
        if len(eager_items) != 1:
            raise ValueError(
                f"ImageStoryboard must have exactly ONE 'eager' image (LCP); "
                f"found {len(eager_items)}."
            )

        min_order = min(i.order for i in self.items)
        if eager_items[0].order != min_order:
            raise ValueError(
                f"The 'eager' image must have the lowest order value. "
                f"Eager has order={eager_items[0].order}, min order={min_order}."
            )

        urls = [i.url for i in self.items]
        if len(urls) != len(set(urls)):
            duplicates = [u for u in urls if urls.count(u) > 1]
            raise ValueError(
                f"Duplicate image URLs in storyboard: {set(duplicates)}"
            )

        return self


class SEOMetadataEntry(BaseModel):
    """Один рядок у seo_metadata.json — метадані для однієї мови."""

    language: str = Field(
        ...,
        pattern=r"^[a-z]{2}-[A-Z]{2}$",
        description="ISO language-region code (e.g., 'en-GB', 'uk-UA', 'es-ES')."
    )
    h1: str = Field(
        ...,
        min_length=3,
        max_length=120,
        description="Clean '[Brand] [Model]' format. NO marketing fluff."
    )
    meta_title: str = Field(
        ...,
        max_length=55,
        description="HARD LIMIT 55 chars. Suffix '| {site_name}' mandatory. "
                    "Max one allowed symbol: ✨ ✅ ➔ ! + % |"
    )
    meta_description: str = Field(
        ...,
        max_length=155,
        description="HARD LIMIT 155 chars. Includes currency symbol + 1 hard "
                    "spec. Ends with localized 'Buy now ➔' (arrow mandatory)."
    )

    @field_validator("meta_description")
    @classmethod
    def _must_end_with_cta_arrow(cls, v: str) -> str:
        if not v.rstrip().endswith("➔"):
            raise ValueError(
                "meta_description must end with the '➔' arrow "
                "(part of the localized CTA, e.g., 'Buy now ➔')."
            )
        return v

    @field_validator("meta_title")
    @classmethod
    def _no_forbidden_emojis(cls, v: str) -> str:
        forbidden_runes = ("📦", "🇺🇸", "🇪🇸", "🇺🇦", "🇵🇱", "🇩🇪", "🇬🇧")
        for rune in forbidden_runes:
            if rune in v:
                raise ValueError(
                    f"meta_title contains forbidden rune {rune!r}. "
                    "Allowed symbols (one max): ✨ ✅ ➔ ! + % |"
                )
        return v


class SEOMetadataBundle(BaseModel):
    """Артефакт seo_metadata.json — bundle для всіх мов одного site."""

    site_name: str = Field(..., description="Target site (e.g., 'EXPERT3D').")
    seo_data: list[SEOMetadataEntry] = Field(
        ...,
        min_length=1,
        description="One entry per target language. Order matches site config."
    )

    @model_validator(mode="after")
    def _no_duplicate_languages(self) -> "SEOMetadataBundle":
        langs = [e.language for e in self.seo_data]
        if len(langs) != len(set(langs)):
            duplicates = [lang for lang in langs if langs.count(lang) > 1]
            raise ValueError(
                f"Duplicate language entries in SEOMetadataBundle: {set(duplicates)}"
            )
        return self
# <<< INSERT BLOCK 1 — END <<<


# =====================================================================
# BLOCK 2 — ECommerceContentCrew: add image_intelligence_analyst agent
# =====================================================================
# Anchor: inside `ECommerceContentCrew.__init__` after the
# `self._frontend_developer = Agent(...)` block.
# Reason: singleton agent instantiation, same pattern as existing agents.
# =====================================================================

# >>> INSERT BLOCK 2 — START >>>
        # ── Image Intelligence Analyst (NEW v2) ───────────────────────
        # Generates ImageStoryboard JSON between QA and html_integration.
        # No tools needed — pure reasoning over tech_specs + copywriting draft.
        self._image_intelligence_analyst = Agent(
            config=agents_config['image_intelligence_analyst'],
            tools=[],
            llm=writer_llm,   # GPT-4o — reuse writer LLM (precise JSON output)
            verbose=True
        )
# <<< INSERT BLOCK 2 — END <<<


# =====================================================================
# BLOCK 3 — ECommerceContentCrew: add image_intelligence_task() method
# =====================================================================
# Anchor: between `quality_assurance_task()` and `html_integration_task()`
# methods in ECommerceContentCrew.
# Reason: image task runs AFTER QA (so it can read approved H2 anchors)
# and BEFORE html_integration (whose context it feeds).
# =====================================================================

# >>> INSERT BLOCK 3 — START >>>
    def image_intelligence_task(self) -> Task:
        """План сториборду зображень: між QA і html_integration.

        Споживає:
          - tech_specs (для Official_Images URL та контексту)
          - copywriting (для H2 anchors у draft)
        Продукує:
          - ImageStoryboard (Pydantic) — типізований план для frontend.
        """
        config = copy.deepcopy(tasks_config['image_intelligence_task'])
        config['description'] = config['description'] + "\n\n{language_instruction}"

        task = Task(
            config=config,
            agent=self._image_intelligence_analyst,
            context=[
                self._require_task('tech_specs'),   # Official_Images URL
                self._require_task('copywriting'),  # H2 anchors з drafted copy
            ],
            output_pydantic=ImageStoryboard,        # Жорстка типізація
        )
        self._tasks['image_intelligence'] = task
        return task
# <<< INSERT BLOCK 3 — END <<<


# =====================================================================
# BLOCK 4 — ECommerceContentCrew: update html_integration_task context
# =====================================================================
# Anchor: REPLACE the existing `html_integration_task()` method body.
# Reason: html_integration now consumes the image storyboard as well.
# Only the `context=` argument changes; everything else stays.
# =====================================================================

# >>> REPLACE BLOCK 4 — START >>>
    def html_integration_task(self) -> Task:
        config = copy.deepcopy(tasks_config['html_integration_task'])
        config['description'] = config['description'] + "\n\n{language_instruction}"

        task = Task(
            config=config,
            agent=self._frontend_developer,
            context=[
                self._require_task('tech_specs'),         # spec tables source of truth
                self._require_task('copywriting'),        # approved copy text
                self._require_task('qa'),                 # verdict (approved status)
                self._require_task('image_intelligence'), # NEW — image storyboard
            ]
        )
        self._tasks['html'] = task
        return task
# <<< REPLACE BLOCK 4 — END <<<


# =====================================================================
# BLOCK 5 — main.py / pipeline_runner.py: include image task in pipeline
# =====================================================================
# Anchor: wherever the Phase 1 task list is built (search for
# `tasks_to_run = [` or `core_crew_module.create_crew([...]`).
# Reason: the new task must be in the sequential pipeline list.
# Apply this in BOTH main.py and pipeline_runner.py if both build the
# task list independently.
# =====================================================================

# >>> EXAMPLE — Phase 1 task list with image task inserted >>>
#
# core_crew_module = ECommerceContentCrew()
# tasks_to_run = [
#     core_crew_module.tech_specs_extraction_task(),
#     core_crew_module.seo_strategy_task(),
#     core_crew_module.copywriting_task(),
#     core_crew_module.quality_assurance_task(),
#     core_crew_module.image_intelligence_task(),   # ← NEW
#     core_crew_module.html_integration_task(),
# ]
# (When auto-search is enabled, prepend url_discovery_task and
#  content_extraction_task as before.)
# <<< EXAMPLE — END <<<


# =====================================================================
# BLOCK 6 — NEW SEOMetadataCrew class
# =====================================================================
# Anchor: ABOVE the existing `MARKET_RULES = {...}` block (i.e., after
# `LocalizationCrew` class definition is complete).
# Reason: this is a separate crew used only by post_pipeline_hook.
# =====================================================================

# >>> INSERT BLOCK 6 — START >>>
class SEOMetadataCrew:
    """Невеликий post-pipeline Crew, що генерує seo_metadata.json bundle.

    Запускається ОДИН РАЗ ПІСЛЯ того, як ВСІ мовні файли (EN base +
    локалізації) згенеровано. Споживає мапу {language: html_content} і
    повертає Pydantic-валідовану SEOMetadataBundle.

    Архітектурно інкапсульовано окремо від ECommerceContentCrew і
    LocalizationCrew — це третя фаза пайплайну (post-pipeline hook).
    """

    def __init__(self) -> None:
        self._extractor = Agent(
            config=agents_config['seo_metadata_extractor'],
            tools=[],
            llm=writer_llm,
            verbose=True
        )

    def seo_metadata_task(self) -> Task:
        return Task(
            config=tasks_config['seo_metadata_extraction_task'],
            agent=self._extractor,
            output_pydantic=SEOMetadataBundle,
        )

    def crew(self, task_callback=None) -> Crew:
        return Crew(
            agents=[self._extractor],
            tasks=[self.seo_metadata_task()],
            process=Process.sequential,
            memory=False,
            cache=True,
            verbose=True,
            task_callback=task_callback,
        )

    def get_inputs(
        self,
        product_name: str,
        site_name: str,
        currency_symbol: str,
        finalized_html_by_language: dict[str, str],
        language_instruction: str = "",
    ) -> dict:
        """Формує inputs для kickoff.

        Args:
            product_name: повна назва продукту.
            site_name: ключ магазину (e.g., 'EXPERT3D').
            currency_symbol: символ валюти ринку (e.g., '€', 'грн', 'zł').
            finalized_html_by_language: {iso_code: html_string}, по одному
                рядку на кожну мову, що має фігурувати у bundle.
            language_instruction: optional — ціль/мова виводу JSON.
        """
        target_languages = sorted(finalized_html_by_language.keys())
        return {
            'product_name': product_name,
            'site_name': site_name,
            'currency_symbol': currency_symbol,
            'target_languages': target_languages,
            'finalized_html_by_language': finalized_html_by_language,
            'language_instruction': language_instruction,
        }
# <<< INSERT BLOCK 6 — END <<<


# =====================================================================
# BLOCK 7 — post_pipeline_hook() orchestration
# =====================================================================
# Anchor: bottom of crew.py, as a module-level function (after all
# class definitions).
# Reason: this is the entry point that pipeline_runner.py calls after
# all language HTML files are written, before ZIP archiving.
# =====================================================================

# >>> INSERT BLOCK 7 — START >>>
import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_seo_metadata_post_hook(
    product_name: str,
    site_name: str,
    currency_symbol: str,
    finalized_html_by_language: dict[str, str],
    output_dir: str,
    task_callback=None,
    cost_tracker=None,
) -> dict:
    """Post-pipeline hook: генерує seo_metadata.json після всіх мовних рандів.

    Args:
        product_name: повна назва продукту.
        site_name: ключ магазину (e.g., 'EXPERT3D').
        currency_symbol: символ валюти ринку.
        finalized_html_by_language: мапа {iso_code: html_string} для всіх
            мов, що ввійдуть у bundle.
        output_dir: директорія для запису seo_metadata.json.
        task_callback: optional CrewAI task callback.
        cost_tracker: optional PipelineCostTracker для телеметрії.

    Returns:
        dict з полями:
            - 'bundle': SEOMetadataBundle | None
            - 'path': str | None — повний шлях до seo_metadata.json або None
            - 'error': str | None
    """
    result: dict = {'bundle': None, 'path': None, 'error': None}

    try:
        seo_crew_module = SEOMetadataCrew()
        seo_inputs = seo_crew_module.get_inputs(
            product_name=product_name,
            site_name=site_name,
            currency_symbol=currency_symbol,
            finalized_html_by_language=finalized_html_by_language,
        )

        seo_crew = seo_crew_module.crew(task_callback=task_callback)
        seo_result = seo_crew.kickoff(inputs=seo_inputs)

        # Cost telemetry (failure-isolated — tracker errors NEVER crash hook)
        if cost_tracker is not None:
            try:
                cost_tracker.register_kickoff(
                    crew_label="Post-pipeline: SEO Metadata",
                    usage_metrics=getattr(seo_crew, "usage_metrics", None),
                    primary_model="gpt-4o",
                    task_outputs=getattr(seo_result, "tasks_output", None),
                )
            except Exception as cost_exc:
                logger.warning(f"SEO metadata cost telemetry failed: {cost_exc}")

        # Pydantic-валідація вже відбулася всередині Task через
        # output_pydantic=SEOMetadataBundle. seo_result.pydantic — це
        # validated instance.
        bundle: SEOMetadataBundle = seo_result.pydantic  # type: ignore
        result['bundle'] = bundle

        seo_json_path = os.path.join(output_dir, 'seo_metadata.json')
        with open(seo_json_path, 'w', encoding='utf-8') as f:
            json.dump(
                bundle.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
            )
        result['path'] = seo_json_path
        logger.info(f"SEO metadata bundle saved: {seo_json_path}")

    except Exception as exc:
        logger.exception("SEO metadata post-hook failed")
        result['error'] = str(exc)

    return result
# <<< INSERT BLOCK 7 — END <<<


# =====================================================================
# BLOCK 8 — pipeline_runner.py: call the hook
# =====================================================================
# Anchor: inside `run_pipeline_headless()`, AFTER the "Крок 2: решта мов"
# loop (i.e., after all language HTML files have been saved), BEFORE
# the "Cost report" block and BEFORE the ZIP archive creation.
# =====================================================================

# >>> INSERT BLOCK 8 — START (illustrative; insert into pipeline_runner.py) >>>
#
#         # ── Post-pipeline: SEO metadata bundle ─────────────────────
#         _log("\n📊 Генерація seo_metadata.json...\n")
#
#         # Збираємо HTML по мовах: {iso_code: html_string}
#         # SITES_CONFIG[site] зберігає 'languages' як ISO codes список.
#         finalized_html_by_language: dict[str, str] = {}
#         for lang_label, html_content in result["files"].items():
#             # lang_label — це user-friendly мітка ('Ukrainian', 'Spanish', etc.)
#             # Конвертуємо до ISO code через мапінг із SITES_CONFIG.
#             iso = _label_to_iso(lang_label, site_info)
#             if iso:
#                 finalized_html_by_language[iso] = html_content
#
#         if finalized_html_by_language:
#             from content_generator.crew import run_seo_metadata_post_hook
#             seo_hook_result = run_seo_metadata_post_hook(
#                 product_name=product_name,
#                 site_name=site,
#                 currency_symbol=site_info.get('currency_symbol', '€'),
#                 finalized_html_by_language=finalized_html_by_language,
#                 output_dir=output_dir,
#                 task_callback=task_cb,
#                 cost_tracker=cost_tracker,
#             )
#             if seo_hook_result.get('path'):
#                 _log(f"💾 SEO metadata збережено: {seo_hook_result['path']}\n")
#                 result["files"]["SEO Metadata"] = seo_hook_result['path']
#             elif seo_hook_result.get('error'):
#                 _log(f"⚠️ SEO metadata generation failed: "
#                      f"{seo_hook_result['error']}\n")
#         else:
#             _log("⚠️ No finalized HTML to extract SEO metadata from.\n")
#
# <<< INSERT BLOCK 8 — END <<<


# =====================================================================
# BLOCK 9 — SITES_CONFIG addendum: currency_symbol per site
# =====================================================================
# Anchor: existing SITES_CONFIG dict in crew.py — add a currency_symbol
# field to each site entry. This is consumed by the SEO metadata hook.
# =====================================================================

# >>> EXAMPLE — SITES_CONFIG entries with currency_symbol >>>
#
# SITES_CONFIG = {
#     "3DDevice": {
#         "country": "Ukraine",
#         "currency_symbol": "грн",   # ← ADD
#         "languages_iso": ["en-GB", "uk-UA", "ru-UA"],   # ← optional but recommended
#         "ua_is_production": True,
#         "localizer": "localizer_ua",
#         ...
#     },
#     "EXPERT3D": {
#         "country": "Spain",
#         "currency_symbol": "€",     # ← ADD
#         "languages_iso": ["en-ES", "es-ES", "uk-UA"],
#         "ua_is_production": False,
#         "localizer": "localizer_es",
#         ...
#     },
#     "Expert-3DPrinter": {
#         "country": "USA",
#         "currency_symbol": "$",     # ← ADD
#         "languages_iso": ["en-US", "es-MX", "uk-UA"],
#         "ua_is_production": False,
#         "localizer": "localizer_us",
#         ...
#     },
#     "Center 3D Print": {
#         "country": "Poland",
#         "currency_symbol": "zł",    # ← ADD (or "€" for EU pages)
#         "languages_iso": ["pl-PL", "en-GB", "de-DE", "uk-UA", "ru-UA"],
#         "ua_is_production": False,
#         "localizer": "localizer_pl",
#         ...
#     },
# }
# <<< EXAMPLE — END <<<


# =====================================================================
# BLOCK 10 — Unit test additions (recommended)
# =====================================================================
# Anchor: add new test class to tests/unit/test_crew_schemas.py
# =====================================================================

# >>> NEW TEST FILE BLOCK — START >>>
#
# class TestImageStoryboard:
#     """v2 — Pydantic invariants for ImageStoryboard."""
#
#     VALID_ITEM = {
#         "url": "https://example.com/img1.jpg",
#         "alt_text": "PUDU HolaBot front view with four illuminated trays "
#                     "showing the 15 kg per tray capacity demonstration",
#         "lead_in_paragraph": "The image below shows the four illuminated trays.",
#         "placement_anchor": "HERO",
#         "loading_strategy": "eager",
#         "order": 1,
#     }
#
#     def test_empty_storyboard_is_valid(self):
#         sb = ImageStoryboard(items=[])
#         assert sb.items == []
#
#     def test_single_eager_image_passes(self):
#         sb = ImageStoryboard(items=[self.VALID_ITEM])
#         assert sb.items[0].loading_strategy == "eager"
#
#     def test_two_eager_images_rejected(self):
#         item2 = {**self.VALID_ITEM, "url": "https://x/img2.jpg", "order": 2}
#         with pytest.raises(ValidationError, match="exactly ONE 'eager'"):
#             ImageStoryboard(items=[self.VALID_ITEM, item2])
#
#     def test_eager_not_min_order_rejected(self):
#         eager_high = {**self.VALID_ITEM, "order": 5}
#         lazy_low = {**self.VALID_ITEM, "url": "https://x/lo.jpg",
#                     "loading_strategy": "lazy", "order": 1}
#         with pytest.raises(ValidationError, match="lowest order"):
#             ImageStoryboard(items=[eager_high, lazy_low])
#
#     def test_duplicate_urls_rejected(self):
#         item2 = {**self.VALID_ITEM, "loading_strategy": "lazy", "order": 2}
#         with pytest.raises(ValidationError, match="Duplicate image URLs"):
#             ImageStoryboard(items=[self.VALID_ITEM, item2])
#
#
# class TestSEOMetadataBundle:
#     """v2 — Pydantic invariants for SEOMetadataBundle."""
#
#     VALID_ENTRY = {
#         "language": "en-GB",
#         "h1": "PUDU HolaBot",
#         "meta_title": "PUDU HolaBot - 60 kg Service Robot | EXPERT3D",
#         "meta_description": "Autonomous service robot, 60 kg payload, "
#                             "SLAM navigation. From €X,XXX. Buy now ➔",
#     }
#
#     def test_valid_bundle_passes(self):
#         bundle = SEOMetadataBundle(site_name="EXPERT3D",
#                                    seo_data=[self.VALID_ENTRY])
#         assert bundle.seo_data[0].language == "en-GB"
#
#     def test_meta_title_over_55_rejected(self):
#         bad = {**self.VALID_ENTRY,
#                "meta_title": "X" * 56}
#         with pytest.raises(ValidationError):
#             SEOMetadataEntry(**bad)
#
#     def test_meta_description_without_arrow_rejected(self):
#         bad = {**self.VALID_ENTRY,
#                "meta_description": "Buy now without the arrow."}
#         with pytest.raises(ValidationError, match="'➔' arrow"):
#             SEOMetadataEntry(**bad)
#
#     def test_meta_description_over_155_rejected(self):
#         bad = {**self.VALID_ENTRY, "meta_description": "X" * 156 + "➔"}
#         with pytest.raises(ValidationError):
#             SEOMetadataEntry(**bad)
#
#     def test_forbidden_emoji_in_title_rejected(self):
#         bad = {**self.VALID_ENTRY,
#                "meta_title": "📦 PUDU HolaBot | EXPERT3D"}
#         with pytest.raises(ValidationError, match="forbidden rune"):
#             SEOMetadataEntry(**bad)
#
#     def test_invalid_iso_code_rejected(self):
#         bad = {**self.VALID_ENTRY, "language": "english"}
#         with pytest.raises(ValidationError):
#             SEOMetadataEntry(**bad)
#
#     def test_duplicate_languages_in_bundle_rejected(self):
#         entry2 = {**self.VALID_ENTRY, "h1": "PUDU HolaBot 2"}
#         with pytest.raises(ValidationError, match="Duplicate language"):
#             SEOMetadataBundle(site_name="EXPERT3D",
#                               seo_data=[self.VALID_ENTRY, entry2])
#
# <<< NEW TEST FILE BLOCK — END <<<
