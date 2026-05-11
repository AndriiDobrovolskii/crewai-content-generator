# STAGE 3 — Pipeline Integration Patches

**Файл:** `src/content_generator/pipeline_runner.py`

Усі зміни — **strictly additive**. Жодна існуюча поведінка не видаляється.
5 touch points + error-path coverage.

---

## Patch 3.1 — Import cost_tracker module

Знайди (на початку файлу, серед існуючих імпортів):
```python
from typing import Any, Callable
```

Заміни на (додай нові імпорти):
```python
from pathlib import Path
from typing import Any, Callable

from content_generator.tools.cost_tracker import PipelineCostTracker
```

---

## Patch 3.2 — Інстанціація tracker'а на початку pipeline

Знайди:
```python
    result: dict[str, Any] = {
        "output_dir": None,
        "zip_path": None,
        "files": {},
        "error": None,
    }

    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)
```

Заміни на:
```python
    result: dict[str, Any] = {
        "output_dir": None,
        "zip_path": None,
        "files": {},
        "error": None,
    }

    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    # ── Cost tracker (failure-isolated; tracker errors NEVER crash pipeline) ──
    try:
        cost_tracker: PipelineCostTracker | None = PipelineCostTracker()
        cost_tracker.set_context(product_name=product_name, site=site)
    except Exception as exc:
        logger.warning(f"Cost tracker init failed — continuing without telemetry: {exc}")
        cost_tracker = None
```

---

## Patch 3.3 — Реєстрація Phase 1 (Core Crew) kickoff'у

Знайди:
```python
        with stdout_ctx:
            active_core_crew = core_crew_module.create_crew(tasks_to_run, task_callback=task_cb)
            core_result = active_core_crew.kickoff(inputs=core_inputs)

        base_english_html = core_result.raw
        english_filename = f"{folder_name}_BASE_English.html"
        _save_html(output_dir, english_filename, base_english_html)
        result["files"]["English (Base)"] = base_english_html
        _log("\n✅ Базовий HTML (English + GEO Microdata) збережено.\n")
```

Заміни на:
```python
        with stdout_ctx:
            active_core_crew = core_crew_module.create_crew(tasks_to_run, task_callback=task_cb)
            core_result = active_core_crew.kickoff(inputs=core_inputs)

        # ── Cost telemetry: Phase 1 ─────────────────────────────────
        if cost_tracker is not None:
            cost_tracker.register_kickoff(
                crew_label="Phase 1: Core",
                usage_metrics=getattr(active_core_crew, "usage_metrics", None),
                primary_model="gpt-4o",
                task_outputs=getattr(core_result, "tasks_output", None),
            )

        base_english_html = core_result.raw
        english_filename = f"{folder_name}_BASE_English.html"
        _save_html(output_dir, english_filename, base_english_html)
        result["files"]["English (Base)"] = base_english_html
        _log("\n✅ Базовий HTML (English + GEO Microdata) збережено.\n")
```

---

## Patch 3.4 — Реєстрація Phase 2 Step 1 (Ukrainian)

Знайди:
```python
        with stdout_ctx:
            ua_crew = ua_crew_module.crew(task_callback=task_cb)
            ua_result = ua_crew.kickoff(inputs=ua_inputs)

        _save_html(output_dir, ua_filename, ua_result.raw)
        result["files"][ua_label] = ua_result.raw
        _log(f"💾 Збережено: {ua_filename}\n")
```

Заміни на:
```python
        with stdout_ctx:
            ua_crew = ua_crew_module.crew(task_callback=task_cb)
            ua_result = ua_crew.kickoff(inputs=ua_inputs)

        # ── Cost telemetry: Phase 2 Step 1 (Ukrainian) ──────────────
        if cost_tracker is not None:
            cost_tracker.register_kickoff(
                crew_label=f"Phase 2: {ua_label}",
                usage_metrics=getattr(ua_crew, "usage_metrics", None),
                primary_model="gpt-4o",
                task_outputs=getattr(ua_result, "tasks_output", None),
            )

        _save_html(output_dir, ua_filename, ua_result.raw)
        result["files"][ua_label] = ua_result.raw
        _log(f"💾 Збережено: {ua_filename}\n")
```

---

## Patch 3.5 — Реєстрація Phase 2 Step 2 (решта мов у loop)

Знайди:
```python
        for language in site_info["languages"]:
            if language == "Ukrainian":
                _log(f"  ⏩ {language} — вже згенеровано, пропуск.\n")
                continue

            _log(f"\n  🔄 Транскреація: {language}...\n")
            loc_crew_module = LocalizationCrew(market_key=localizer_key)
            loc_inputs = loc_crew_module.get_inputs(
                product_name=product_name,
                site_name=site,
                target_language=language,
                base_html=base_english_html,
            )
            with stdout_ctx:
                loc_crew = loc_crew_module.crew(task_callback=task_cb)
                loc_result = loc_crew.kickoff(inputs=loc_inputs)

            safe_lang = language.split(" ")[0]
            filename = f"{folder_name}_{safe_lang}.html"
            _save_html(output_dir, filename, loc_result.raw)
            result["files"][language] = loc_result.raw
            _log(f"  💾 Збережено: {filename}\n")
```

Заміни на:
```python
        for language in site_info["languages"]:
            if language == "Ukrainian":
                _log(f"  ⏩ {language} — вже згенеровано, пропуск.\n")
                continue

            _log(f"\n  🔄 Транскреація: {language}...\n")
            loc_crew_module = LocalizationCrew(market_key=localizer_key)
            loc_inputs = loc_crew_module.get_inputs(
                product_name=product_name,
                site_name=site,
                target_language=language,
                base_html=base_english_html,
            )
            with stdout_ctx:
                loc_crew = loc_crew_module.crew(task_callback=task_cb)
                loc_result = loc_crew.kickoff(inputs=loc_inputs)

            # ── Cost telemetry: Phase 2 Step 2 (per-language) ──────
            if cost_tracker is not None:
                cost_tracker.register_kickoff(
                    crew_label=f"Phase 2: {language}",
                    usage_metrics=getattr(loc_crew, "usage_metrics", None),
                    primary_model="gpt-4o",
                    task_outputs=getattr(loc_result, "tasks_output", None),
                )

            safe_lang = language.split(" ")[0]
            filename = f"{folder_name}_{safe_lang}.html"
            _save_html(output_dir, filename, loc_result.raw)
            result["files"][language] = loc_result.raw
            _log(f"  💾 Збережено: {filename}\n")
```

---

## Patch 3.6 — Dump cost report ПЕРЕД ZIP-архівацією

Знайди:
```python
        # ── ZIP-архів ────────────────────────────────────────────────────
        _log("\n📦 Створення ZIP-архіву...\n")
        zip_base = os.path.join("output", folder_name)
        shutil.make_archive(zip_base, "zip", output_dir)
        zip_path = os.path.join(output_dir, f"{folder_name}.zip")
        shutil.move(f"{zip_base}.zip", zip_path)
        result["zip_path"] = zip_path
```

Заміни на:
```python
        # ── Cost report ───────────────────────────────────────────────────
        if cost_tracker is not None:
            try:
                cost_tracker.to_console(_log)
                cost_report_path = os.path.join(output_dir, "cost_report.json")
                if cost_tracker.to_json(Path(cost_report_path)) is not None:
                    _log(f"💾 Cost report збережено: {cost_report_path}\n")
                    result["files"]["Cost Report"] = cost_report_path
            except Exception as cost_exc:
                logger.warning(f"Cost report dump failed: {cost_exc}")

        # ── ZIP-архів ────────────────────────────────────────────────────
        _log("\n📦 Створення ZIP-архіву...\n")
        zip_base = os.path.join("output", folder_name)
        shutil.make_archive(zip_base, "zip", output_dir)
        zip_path = os.path.join(output_dir, f"{folder_name}.zip")
        shutil.move(f"{zip_base}.zip", zip_path)
        result["zip_path"] = zip_path
```

---

## Patch 3.7 — Error path: partial cost report при padінні

Знайди:
```python
    except Exception as exc:
        logger.exception("Pipeline error")
        result["error"] = str(exc)
        _log(f"\n❌ ПОМИЛКА: {exc}\n")

    return result
```

Заміни на:
```python
    except Exception as exc:
        logger.exception("Pipeline error")
        result["error"] = str(exc)
        _log(f"\n❌ ПОМИЛКА: {exc}\n")

        # Partial cost report навіть при падінні — forensic data
        if cost_tracker is not None and result.get("output_dir"):
            try:
                partial_path = os.path.join(
                    result["output_dir"], "cost_report_PARTIAL.json"
                )
                cost_tracker.to_json(Path(partial_path))
                _log(f"💾 Partial cost report (до помилки): {partial_path}\n")
            except Exception:
                pass  # Failed forensic dump — silently skip

    return result
```

---

## ✓ Verification

```bash
# 1. Імпорт працює
uv run python -c "from content_generator.tools.cost_tracker import PipelineCostTracker; print('OK')"
# Очікую: OK

# 2. Pricing config валідний
uv run python -c "from content_generator.tools.cost_tracker import PipelineCostTracker; t = PipelineCostTracker(); print(list(t._pricing_models.keys()))"
# Очікую: ['gpt-4o', 'gpt-4o-mini', 'text-embedding-3-small', 'gemini-1.5-pro']

# 3. Юніт-тести
uv run pytest tests/unit/test_cost_tracker.py -v
# Очікую: 22 passed

# 4. Pipeline syntax check
uv run python -c "from content_generator.pipeline_runner import run_pipeline_headless; print('OK')"
# Очікую: OK

# 5. Smoke test — 1 продукт на 3DDevice (4 kickoff-и, найдешевший варіант)
uv run src/content_generator/main.py
# Очікую:
# - cost_report.json з'являється у output/<folder>/
# - У console вкінці — таблиця з PIPELINE COST REPORT
# - total_cost_usd > 0

# 6. Manual sanity: відкрити OpenAI usage dashboard після smoke test
# Очікую: total_cost_usd має бути в межах ±10% від суми у dashboard
```
