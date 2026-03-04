import os
import yaml
from typing import Any, List, Dict, Optional, Union
from pydantic import BaseModel, Field, field_validator
from crewai import Agent, Crew, Process, Task, LLM
from crewai_tools import SerperDevTool, WebsiteSearchTool, PDFSearchTool

# Оновлені імпорти (оскільки tools.py тепер у папці tools/)
from tools.custom_tools import ContentSimilarityTool, USMeasurementCalculatorTool

# --- ДИНАМІЧНІ ШЛЯХИ ДО КОНФІГІВ ---
# Отримуємо шлях до папки, де лежить сам файл crew.py
current_dir = os.path.dirname(os.path.abspath(__file__))

agents_config_path = os.path.join(current_dir, 'config', 'agents.yaml')
tasks_config_path = os.path.join(current_dir, 'config', 'tasks.yaml')

# Завантажуємо конфігурації за абсолютними шляхами
with open(agents_config_path, 'r', encoding='utf-8') as f:
    agents_config = yaml.safe_load(f)
with open(tasks_config_path, 'r', encoding='utf-8') as f:
    tasks_config = yaml.safe_load(f)

# =====================================================================
# ⚙️ НАЛАШТУВАННЯ LLM
# =====================================================================
# Для тестування використовуємо одну модель. 
# ВАЖЛИВО: Для ієрархічного процесу (Hierarchical) Менеджер МАЄ бути розумним.
# Завантажуємо назви моделей з .env (з фолбеком на дефолтні значення, якщо змінної немає)
default_model_name = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
manager_model_name = os.getenv("MANAGER_MODEL", "gpt-4o")

# Ініціалізуємо LLM
default_llm = LLM(model=default_model_name)
manager_llm = LLM(model=manager_model_name)


# =====================================================================
# 🛡️ PYDANTIC СХЕМИ ДЛЯ ЖОРСТКОЇ ТИПІЗАЦІЇ (Guardrails)
# =====================================================================
class SupportData(BaseModel):
    faqs: List[Dict[str, str]] = Field(default_factory=list, description="Array of FAQs found in the text. Format: [{'Question': '...', 'Answer': '...'}]")
    troubleshooting: List[Dict[str, str]] = Field(default_factory=list, description="Array of troubleshooting steps or guides found.")

class TechSpecsOutput(BaseModel):
    Technical_Specifications: Dict[str, Dict[str, str]] = Field(
        ..., 
        description="MUST be a NESTED dictionary. Top-level keys are Categories (e.g., 'Printing', 'Power'). Inner keys are Specification Names (e.g., 'Nozzle Temp'). Values are the specs."
    )
    Support_Data: SupportData = Field(..., description="Extracted FAQs and Troubleshooting data for GEO schema generation")

    @field_validator('Technical_Specifications', mode='before')
    @classmethod
    def normalize_spec_values(cls, specs: Any) -> Any:
        """Convert any list values inside spec categories to comma-separated strings."""
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
                # Edge case: category value is itself a list
                normalized[category] = {'value': ', '.join(str(i) for i in fields)}
            else:
                normalized[category] = fields
        return normalized


# =====================================================================
# 🏭 ФАЗА 1: CORE CONTENT CREW
# =====================================================================
class ECommerceContentCrew:
    """Core Content Generation Crew (Фаза 1)"""
    
    # --- ІНІЦІАЛІЗАЦІЯ АГЕНТІВ ---
    def web_researcher(self) -> Agent:
        return Agent(
            config=agents_config['web_researcher'],
            # RAG-інструменти для глибокого семантичного пошуку по сторінках і мануалах
            tools=[SerperDevTool(), WebsiteSearchTool(), PDFSearchTool()], 
            llm=default_llm,
            verbose=True
        )

    def tech_specs_analyst(self) -> Agent:
        return Agent(
            config=agents_config['tech_specs_analyst'],
            llm=default_llm,
            verbose=True
        )

    def seo_strategist(self) -> Agent:
        return Agent(
            config=agents_config['seo_strategist'],
            tools=[SerperDevTool()], # ДОДАНО ІНСТРУМЕНТ! Тепер він має доступ до Google
            llm=default_llm,
            verbose=True
        )

    def copywriter(self) -> Agent:
        return Agent(
            config=agents_config['copywriter'],
            llm=default_llm,
            verbose=True
        )

    def editor_qa(self) -> Agent:
        return Agent(
            config=agents_config['editor_qa'],
            tools=[ContentSimilarityTool()],
            llm=default_llm,
            verbose=True
        )

    def frontend_developer(self) -> Agent:
        return Agent(
            config=agents_config['frontend_developer'],
            llm=default_llm,
            verbose=True
        )

    # --- ІНІЦІАЛІЗАЦІЯ ЗАВДАНЬ ---
    def source_research_task(self) -> Task:
        return Task(
            config=tasks_config['source_research_task'],
            agent=self.web_researcher(),
            human_input=True
        )

    def tech_specs_extraction_task(self) -> Task:
        config = tasks_config['tech_specs_extraction_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"
        return Task(
            config=config,
            agent=self.tech_specs_analyst(),
            output_pydantic=TechSpecsOutput # ЖОРСТКИЙ КОНТРОЛЬ СИНТАКСИСУ (Захист від галюцинацій)
        )

    def seo_strategy_task(self) -> Task:
        config = tasks_config['seo_strategy_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"
        return Task(
            config=config,
            agent=self.seo_strategist()
        )

    def copywriting_task(self) -> Task:
        config = tasks_config['copywriting_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"
        return Task(
            config=config,
            agent=self.copywriter()
        )

    def quality_assurance_task(self) -> Task:
        config = tasks_config['quality_assurance_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"
        return Task(
            config=config,
            agent=self.editor_qa()
        )

    def html_integration_task(self) -> Task:
        config = tasks_config['html_integration_task'].copy()
        config['description'] = config['description'] + "\n\n{language_instruction}"
        return Task(
            config=config,
            agent=self.frontend_developer()
        )

    @property
    def agents(self):
        return[
            self.web_researcher(),
            self.tech_specs_analyst(),
            self.seo_strategist(),
            self.copywriter(),
            self.editor_qa(),
            self.frontend_developer()
        ]

    def create_crew(self, tasks_to_run: list) -> Crew:
        """Створює Crew з послідовним процесом для гарантії Human-in-the-Loop"""
        return Crew(
            agents=self.agents,
            tasks=tasks_to_run,
            process=Process.sequential, # ПОВЕРНУЛИ НА SEQUENTIAL!
            memory=True,                # Пам'ять залишається
            cache=True,                 # Кеш залишається
            verbose=True
        )


# =====================================================================
# 🌍 ФАЗА 2: LOCALIZATION CREW
# =====================================================================
class LocalizationCrew:
    """Crew для локалізації (Фаза 2)"""
    
    def __init__(self, localizer_name: str):
        self.localizer_name = localizer_name

    def localizer_agent(self) -> Agent:
        # Базові налаштування
        agent_tools =[]
        
        # Якщо це ринок США - видаємо агенту математичний інструмент конвертації
        if self.localizer_name == 'localizer_us':
            agent_tools.append(USMeasurementCalculatorTool())

        return Agent(
            config=agents_config[self.localizer_name],
            tools=agent_tools,
            # ЗМІНЕНО ТУТ: Використовуємо manager_llm (gpt-4o), 
            # бо робота з HTML-тегами та мікророзміткою при перекладі потребує високого IQ моделі!
            llm=manager_llm, 
            verbose=True
        )

    def localization_task(self) -> Task:
        return Task(
            config=tasks_config['localization_task'],
            agent=self.localizer_agent()
        )

    def crew(self) -> Crew:
        return Crew(
            agents=[self.localizer_agent()],
            tasks=[self.localization_task()],
            process=Process.sequential, 
            memory=True,
            cache=True,
            verbose=True
        )