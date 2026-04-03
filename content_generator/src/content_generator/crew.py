import os
import yaml
from typing import Any, List, Dict, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from crewai import Agent, Crew, Process, Task, LLM
from crewai_tools import SerperDevTool, WebsiteSearchTool, PDFSearchTool

# Імпорт кастомних інструментів
try:
    from content_generator.tools.custom_tools import ContentSimilarityTool, USMeasurementCalculatorTool
except ImportError:
    from .tools.custom_tools import ContentSimilarityTool, USMeasurementCalculatorTool


# =====================================================================
# 📂 ЗАВАНТАЖЕННЯ КОНФІГУРАЦІЙ
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
agents_config_path = os.path.join(current_dir, 'config', 'agents.yaml')
tasks_config_path = os.path.join(current_dir, 'config', 'tasks.yaml')

with open(agents_config_path, 'r', encoding='utf-8') as f:
    agents_config = yaml.safe_load(f)
with open(tasks_config_path, 'r', encoding='utf-8') as f:
    tasks_config = yaml.safe_load(f)


# =====================================================================
# ⚙️ НАЛАШТУВАННЯ LLM
# =====================================================================
# Розділення моделей за типом задачі ("Парадокс надійності"):
# - gpt-4o-mini: пошук (дешевий, швидкий)
# - gemini-1.5-pro: аналіз техспек (великий контекст для JSON)
# - gpt-4o: копірайтинг, SEO, HTML, локалізація (висока точність)

researcher_llm = LLM(model=os.getenv("RESEARCHER_MODEL", "gpt-4o-mini"))
analyst_llm = LLM(model=os.getenv("ANALYST_MODEL", "gemini/gemini-1.5-pro"))
writer_llm = LLM(model=os.getenv("WRITER_MODEL", "gpt-4o"))
frontend_llm = LLM(model=os.getenv("FRONTEND_MODEL", "gpt-4o"))
localizer_llm = LLM(model=os.getenv("LOCALIZER_MODEL", "gpt-4o"))


# =====================================================================
# 🛡️ PYDANTIC СХЕМИ (Guardrails)
# =====================================================================

class SupportData(BaseModel):
    faqs: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Array of FAQs: [{'Question': '...', 'Answer': '...'}]"
    )
    troubleshooting: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Array of troubleshooting steps or guides."
    )


class ProductImage(BaseModel):
    url: str = Field(..., description="Exact absolute URL of the official image.")
    alt_text: str = Field(..., description="Descriptive alt text for SEO.")
    context: str = Field(..., description="Where this image belongs (e.g., 'Main Product', 'Speed Showcase').")


class KeyFeature(BaseModel):
    """Ключова перевага продукту для покупця."""
    feature_name: str = Field(..., description="Short feature name (e.g., 'Print Speed', 'Build Volume').")
    spec_value: str = Field(..., description="Exact metric value (e.g., '600 mm/s', '300×300×300 mm').")
    benefit: str = Field(..., description="Why this matters to the buyer (1-2 sentences).")


class TechSpecsOutput(BaseModel):
    """Жорстка схема для виходу аналітика техспек."""
    Technical_Specifications: Dict[str, Dict[str, str]] = Field(
        ...,
        description="NESTED dict grouped by categories. Values MUST be physical metrics (mm, °C, MPa, kg)."
    )
    Key_Features: List[KeyFeature] = Field(
        ...,
        min_length=3,
        max_length=8,
        description=(
            "Top 3-8 selling features of the product with exact metrics and buyer benefits. "
            "These are NOT all specs — only the STRONGEST competitive advantages."
        )
    )
    Marketing_Content: str = Field(
        ...,
        description=(
            "The FULL original marketing/descriptive text from the source, "
            "preserving all product narratives, use cases, and feature explanations. "
            "This is NOT specs — this is the story/copy the manufacturer wrote about the product."
        )
    )
    Support_Data: SupportData = Field(
        ...,
        description="Extracted FAQs and Troubleshooting data for GEO schema generation."
    )
    Official_Images: List[ProductImage] = Field(
        default_factory=list,
        description="List of official product images found in the source text."
    )

    @field_validator('Technical_Specifications', mode='before')
    @classmethod
    def normalize_spec_values(cls, specs: Any) -> Any:
        """Конвертує list-значення всередині категорій у comma-separated strings."""
        if not isinstance(specs, dict):
            return specs
        normalized = {}
        for category, fields in specs.items():
            if isinstance(fields, dict):
                normalized[category] = {
                    k: ', '.join(v) if isinstance(v, list) else str(v)
                    for k, v in fields.items()
                }
            elif isinstance(fields, list):
                normalized[category] = {'value': ', '.join(str(i) for i in fields)}
            else:
                normalized[category] = fields
        return normalized


class QAVerdict(BaseModel):
    """Структурований вердикт QA-редактора. Робить REJECT/APPROVE детерміновано парсабельним."""
    status: Literal["APPROVED", "REJECTED"] = Field(
        ..., description="Final verdict: APPROVED or REJECTED."
    )
    uniqueness_score: float = Field(
        ..., ge=0, le=100,
        description="Uniqueness percentage from the Similarity Tool."
    )
    fact_errors: List[str] = Field(
        default_factory=list,
        description="List of specific factual inaccuracies found."
    )
    external_links_found: List[str] = Field(
        default_factory=list,
        description="List of forbidden external URLs found in the draft."
    )
    missing_sections: List[str] = Field(
        default_factory=list,
        description="Required sections (e.g., FAQ, Troubleshooting) missing from the draft."
    )
    # ВИДАЛЕНО ПОЛЕ approved_text !!!
    expert_insight_present: bool = Field(
        default=False,
        description="Whether an Expert Verdict block with at least one cited metric is present."
    )
    technical_tip_present: bool = Field(
        default=False,
        description="Whether a practitioner-level Technical Tip blockquote is present."
    )


# =====================================================================
# 🌍 РИНКОВО-СПЕЦИФІЧНІ ПРАВИЛА ЛОКАЛІЗАЦІЇ
# =====================================================================
# Інжектуються у {market_rules} задачі localization_task.
# Один агент (localizer_generic) + різні інструкції = менше дублювання.
# =====================================================================

MARKET_RULES = {
    "localizer_ua": """
UKRAINIAN MARKET RULES (UA):
- Punctuation: word after colon (:) starts with lowercase, unless a proper noun.
- Logistics: Use Nova Poshta / Ukrposhta for delivery references.
- Audience: Ukrainian engineers, makers, small businesses.
- Terminology: Use professional Ukrainian 3D printing terminology.
- Do NOT default to Russian unless {target_language} explicitly requires it.
""",

    "localizer_pl": """
POLISH / EU MARKET RULES (PL):
- Logistics: Use DPD / InPost for delivery references. Mention fast European shipping.
- Audience: Polish engineers, German industrial buyers, Eastern European makers.
- Warranty: Reference strict EU warranty standards where appropriate.
- Do NOT default to Polish unless {target_language} is "Polish".
""",

    "localizer_es": """
SPANISH MARKET RULES (ES — Castilian es-ES):
- Geography: Replace any Ukraine/Poland mentions with "España" or "Valencia".
- Logistics: Use "envío urgente 24/48h" for delivery references. Remove UAH/USD prices.
- Castilian Style: Use "Tú" (tuteo). Use es-ES vocabulary: Ordenador, Móvil, Resina, Laminador, Cama caliente.
- Do NOT use Latin American terms.
""",

    "localizer_us": """
US MARKET RULES (USA):
- Geography: Replace Ukraine/Europe with "USA" or "Houston". Replace foreign carriers with UPS/FedEx.
- MEASUREMENT SYSTEM (CRITICAL): 
  * CONVERT to Imperial + metric in parentheses: Dimensions/Build Volume → inches, Weight → lbs.
  * KEEP strictly in Metric: Layer Thickness, Filament/Nozzle Diameter, Temperature (°C — NEVER Fahrenheit), Print Speed.
  * You MUST use the US Measurement Calculator tool for exact conversions.
- Tone: Break long sentences into punchy, direct ones typical of US marketing. Active voice. Benefits-first.
""",

    # Спеціальний набір правил для UA review-версії (без ринково-специфічних адаптацій)
    "review_ua": """
INTERNAL REVIEW VERSION (Ukrainian):
- This is an internal review translation for QA purposes.
- Do NOT adapt geography, logistics, or pricing to any specific market.
- Translate the content into natural Ukrainian, preserving all technical accuracy.
- Focus on clarity and readability for internal reviewers who are not native English speakers.
- Preserve the EXACT same structure, sections, and facts as the English source.
"""
}


# =====================================================================
# 📢 CTA ШАБЛОНИ ДЛЯ МАГАЗИНІВ
# =====================================================================
# Інжектуються у {cta_context} задачі copywriting_task.
# Копірайтер використовує ці факти для секції "Чому купувати у нас".
# =====================================================================

CTA_TEMPLATES = {
    "3DDevice": {
        "store_advantages": [
            "Official authorized dealer in Ukraine",
            "Free shipping via Nova Poshta across Ukraine",
            "Expert technical support from certified 3D printing engineers",
            "Warranty service with local repair center in Kyiv",
            "Free consultation on material selection and printer setup",
        ],
        "urgency_hook": "Order today — same-day dispatch for in-stock items."
    },
    "3DPrinter": {
        "store_advantages": [
            "Largest selection of 3D printers in Ukraine",
            "Price match guarantee against authorized dealers",
            "Free test prints available before purchase",
            "Professional setup and calibration assistance",
            "Loyalty program with discounts on filaments and spare parts",
        ],
        "urgency_hook": "Limited stock — secure yours with a quick order."
    },
    "3DScanner": {
        "store_advantages": [
            "Specialized 3D scanning and printing expertise",
            "Complete scanning-to-printing workflow solutions",
            "On-site demonstrations available in Kyiv",
            "Post-sale scanning software training included",
            "Trade-in program for older equipment",
        ],
        "urgency_hook": "Book a free demo and see the results before you buy."
    },
    "Center 3D Print": {
        "store_advantages": [
            "Fast EU delivery via DPD/InPost (2-5 business days)",
            "Full EU warranty with local support in Poland",
            "Multilingual technical support (PL/DE/EN/UA)",
            "B2B invoicing and bulk order discounts available",
            "Showroom in Warsaw with live printer demonstrations",
        ],
        "urgency_hook": "Order now — EU warehouse ships within 24 hours."
    },
    "EXPERT3D": {
        "store_advantages": [
            "Envío urgente 24/48h en toda España peninsular",
            "Soporte técnico profesional en castellano",
            "Garantía oficial con servicio técnico en Valencia",
            "Financiación disponible para empresas y profesionales",
            "Showroom con demostraciones en vivo en Valencia",
        ],
        "urgency_hook": "Pide hoy — envío en 24h para productos en stock."
    },
    "Expert-3DPrinter": {
        "store_advantages": [
            "Free shipping across the continental US (UPS/FedEx)",
            "30-day hassle-free return policy",
            "US-based technical support team in Houston, TX",
            "Extended warranty options available at checkout",
            "Volume discounts for educational institutions and businesses",
        ],
        "urgency_hook": "Ships same day from our Houston warehouse — order before 2 PM CT."
    },
}


# =====================================================================
# 🗺️ КОНФІГУРАЦІЯ МАГАЗИНІВ
# =====================================================================
# ua_is_production: True = українська версія є і review, і production.
#                   False = українська генерується як REVIEW_Ukrainian (не публікується).
# =====================================================================

SITES_CONFIG = {
    "3DDevice": {
        "country": "Ukraine",
        "languages": ["Ukrainian", "English", "Russian"],
        "localizer": "localizer_ua",
        "ua_is_production": True
    },
    "3DPrinter": {
        "country": "Ukraine",
        "languages": ["Ukrainian", "English", "Russian"],
        "localizer": "localizer_ua",
        "ua_is_production": True
    },
    "3DScanner": {
        "country": "Ukraine",
        "languages": ["Ukrainian", "English", "Russian"],
        "localizer": "localizer_ua",
        "ua_is_production": True
    },
    "Center 3D Print": {
        "country": "Poland",
        "languages": ["Polish", "German", "English", "Ukrainian", "Russian"],
        "localizer": "localizer_pl",
        "ua_is_production": False
    },
    "EXPERT3D": {
        "country": "Spain",
        "languages": ["Spanish (Castilian es-ES)"],
        "localizer": "localizer_es",
        "ua_is_production": False
    },
    "Expert-3DPrinter": {
        "country": "USA",
        "languages": ["American English", "US Spanish"],
        "localizer": "localizer_us",
        "ua_is_production": False
    }
}


# =====================================================================
# 🏭 ФАЗА 1: CORE CONTENT CREW
# =====================================================================

class ECommerceContentCrew:
    """
    Core Content Generation Crew (Фаза 1).
    
    Використовує Singleton Pattern для агентів — кожен агент створюється ОДИН раз
    в __init__ і перевикористовується у всіх задачах та Crew.
    """

    def __init__(self):
        # ---- SINGLETON AGENTS ----
        self._web_researcher = Agent(
            config=agents_config['web_researcher'],
            tools=[SerperDevTool(), WebsiteSearchTool(), PDFSearchTool()],
            llm=researcher_llm,
            verbose=True
        )
        self._tech_specs_analyst = Agent(
            config=agents_config['tech_specs_analyst'],
            llm=analyst_llm,
            verbose=True
        )
        self._seo_strategist = Agent(
            config=agents_config['seo_strategist'],
            tools=[SerperDevTool()],
            llm=writer_llm,
            verbose=True
        )
        self._copywriter = Agent(
            config=agents_config['copywriter'],
            llm=writer_llm,
            verbose=True
        )
        self._editor_qa = Agent(
            config=agents_config['editor_qa'],
            tools=[ContentSimilarityTool()],
            llm=writer_llm,
            verbose=True
        )
        self._frontend_developer = Agent(
            config=agents_config['frontend_developer'],
            llm=frontend_llm,
            verbose=True
        )

        # ---- TASK REFERENCES (для context chaining) ----
        self._tasks: Dict[str, Task] = {}

    # --- Допоміжні методи ---
    def _is_filament(self, product_name: str) -> bool:
        filament_keywords = [
            'pla', 'petg', 'abs', 'asa', 'tpu', 'nylon',
            'carbon', 'filament', 'resin', 'kg', 'spool'
        ]
        return any(kw in product_name.lower() for kw in filament_keywords)

    # --- ІНІЦІАЛІЗАЦІЯ ЗАДАЧ ---

    def url_discovery_task(self, product_name: str) -> Task:
        task = Task(
            config=tasks_config['url_discovery_task'],
            agent=self._web_researcher,
            human_input=True  # 🛑 Зупинка №1: оператор перевіряє URL
        )
        self._tasks['url_discovery'] = task
        return task

    def content_extraction_task(self, product_name: str) -> Task:
        task = Task(
            config=tasks_config['content_extraction_task'],
            agent=self._web_researcher,
            context=[self._tasks['url_discovery']],  # ← Явна залежність
            human_input=True  # 🛑 Зупинка №2: оператор перевіряє контент
        )
        self._tasks['content_extraction'] = task
        return task

    # --- GUI-SAFE AUTO-SEARCH (без human_input) ---

    def url_discovery_task_headless(self, product_name: str) -> Task:
        """URL discovery без human_input — для GUI auto-search."""
        task = Task(
            config=tasks_config['url_discovery_task'],
            agent=self._web_researcher,
            human_input=False  # ← GUI-safe: без блокуючого input()
        )
        self._tasks['url_discovery'] = task
        return task

    def create_discovery_crew(self, product_name: str, task_callback=None) -> Crew:
        """Мінімальний Crew тільки для URL discovery (Phase 0).

        Повертає Crew з одним агентом і одною задачею.
        Використовується GUI для пошуку URL перед основним pipeline.
        """
        task = self.url_discovery_task_headless(product_name)
        return Crew(
            agents=[self._web_researcher],
            tasks=[task],
            process=Process.sequential,
            memory=False,   # Не потрібна пам'ять для одноразового пошуку
            cache=True,
            verbose=True,
            task_callback=task_callback
        )

    def tech_specs_extraction_task(self, product_name: str) -> Task:
        config = tasks_config['tech_specs_extraction_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"

        if self._is_filament(product_name):
            config['description'] += (
                "\n\nREQUIRED MATERIAL SPECS: Density, Melt Flow Index, "
                "Impact Strength, Heat Deflection, and Diameter Tolerance."
            )

        # Context: залежить від content_extraction якщо він існує (auto-search)
        ctx = []
        if 'content_extraction' in self._tasks:
            ctx.append(self._tasks['content_extraction'])

        task = Task(
            config=config,
            agent=self._tech_specs_analyst,
            context=ctx if ctx else None,
            output_pydantic=TechSpecsOutput  # ← Жорстка типізація
        )
        self._tasks['tech_specs'] = task
        return task

    def seo_strategy_task(self) -> Task:
        config = tasks_config['seo_strategy_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"

        task = Task(
            config=config,
            agent=self._seo_strategist,
            context=[self._tasks['tech_specs']]  # ← Отримує структурований JSON
        )
        self._tasks['seo_strategy'] = task
        return task

    def copywriting_task(self) -> Task:
        config = tasks_config['copywriting_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"

        task = Task(
            config=config,
            agent=self._copywriter,
            context=[
                self._tasks['tech_specs'],    # ← Сирі специфікації (ground truth)
                self._tasks['seo_strategy']   # ← SEO-бриф зі структурою H2/H3
            ]
        )
        self._tasks['copywriting'] = task
        return task

    def quality_assurance_task(self) -> Task:
        config = tasks_config['quality_assurance_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"

        task = Task(
            config=config,
            agent=self._editor_qa,
            context=[
                self._tasks['tech_specs'],   # ← Ground truth для перевірки фактів
                self._tasks['copywriting']   # ← Чернетка для рев'ю
            ],
            output_pydantic=QAVerdict  # ← Структурований вердикт
        )
        self._tasks['qa'] = task
        return task

    def html_integration_task(self) -> Task:
        config = tasks_config['html_integration_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"

        task = Task(
            config=config,
            agent=self._frontend_developer,
            context=[
                self._tasks['tech_specs'],  # ← Для таблиці специфікацій + зображення
                self._tasks['copywriting'], # ← ДОДАНО! HTML-кодер бере текст напряму від копірайтера
                self._tasks['qa']           # ← Отримує вердикт QA (щоб знати, що текст approved)
            ]
        )
        self._tasks['html'] = task
        return task


    def create_crew(self, tasks_to_run: list, task_callback=None) -> Crew:
        """Створює Crew з послідовним процесом."""
        # Збираємо унікальних агентів з задач (без дублікатів)
        unique_agents = []
        seen_ids = set()
        for task in tasks_to_run:
            agent_id = id(task.agent)
            if agent_id not in seen_ids:
                unique_agents.append(task.agent)
                seen_ids.add(agent_id)

        return Crew(
            agents=unique_agents,
            tasks=tasks_to_run,
            process=Process.sequential,
            memory=False,
            cache=True,
            verbose=True,
            task_callback=task_callback
        )


# =====================================================================
# 🌍 ФАЗА 2: LOCALIZATION CREW (параметризований)
# =====================================================================

class LocalizationCrew:
    """
    Параметризований Crew для локалізації (Фаза 2).
    
    Один агент (localizer_generic) + ринково-специфічні правила 
    з MARKET_RULES, що інжектуються у {market_rules} задачі.
    """

    def __init__(self, market_key: str):
        """
        Args:
            market_key: Ключ з MARKET_RULES (e.g., 'localizer_ua', 'localizer_us', 'review_ua')
        """
        self.market_key = market_key

        # Визначаємо інструменти залежно від ринку
        agent_tools = []
        if market_key == 'localizer_us':
            agent_tools.append(USMeasurementCalculatorTool())

        self._localizer = Agent(
            config=agents_config['localizer_generic'],
            tools=agent_tools,
            llm=localizer_llm,
            verbose=True
        )

    def _get_market_rules(self) -> str:
        """Повертає ринково-специфічні правила для інжекції в задачу."""
        rules = MARKET_RULES.get(self.market_key, "")
        if not rules:
            raise ValueError(
                f"Unknown market_key: '{self.market_key}'. "
                f"Available keys: {list(MARKET_RULES.keys())}"
            )
        return rules

    def localization_task(self) -> Task:
        return Task(
            config=tasks_config['localization_task'],
            agent=self._localizer
        )

    def crew(self, task_callback=None) -> Crew:
        return Crew(
            agents=[self._localizer],
            tasks=[self.localization_task()],
            process=Process.sequential,
            memory=True,
            cache=True,
            verbose=True,
            task_callback=task_callback
        )

    def get_inputs(self, product_name: str, site_name: str,
                   target_language: str, base_html: str) -> dict:
        """Формує повний набір inputs для kickoff, включаючи market_rules."""
        return {
            'product_name': product_name,
            'site_name': site_name,
            'target_language': target_language,
            'base_html': base_html,
            'market_rules': self._get_market_rules()
        }