# Промпты для запуска Analyst

## Задача 001: LLM Gateway - Queue и Batch Executor

```
Ты — агент Analyst (см. .agents/analyst.md).

Прочитай:
- .agents/analyst.md
- AGENTS.md
- 00_docs/architecture/overview.md
- 00_docs/architecture/implementation_plan.md
- 00_docs/standards/common/*
- 00_docs/standards/analyst/*
- 01_tasks/001_llm_gateway/task_brief_01.md

Задача: Создай техническое задание в 01_tasks/001_llm_gateway/analysis_01.md
с учетом интерфейсов и модулей из implementation plan.

После завершения сформируй промпт для Developer.
```

## Задача 004: SGR Agent Core интеграция

```
Ты — агент Analyst (см. .agents/analyst.md).

Прочитай:
- .agents/analyst.md
- AGENTS.md
- 00_docs/architecture/overview.md
- 00_docs/architecture/implementation_plan.md
- 00_docs/standards/common/*
- 00_docs/standards/analyst/*
- 01_tasks/004_sgr_integration/task_brief_01.md

Задача: Создай техническое задание в 01_tasks/004_sgr_integration/analysis_01.md
с учетом интерфейсов и модулей из implementation plan.

После завершения сформируй промпт для Developer.
```

## Задача 006: Document Skeleton - структуры данных

```
Ты — агент Analyst (см. .agents/analyst.md).

Прочитай:
- .agents/analyst.md
- AGENTS.md
- 00_docs/architecture/overview.md
- 00_docs/architecture/implementation_plan.md
- 00_docs/standards/common/*
- 00_docs/standards/analyst/*
- 01_tasks/006_document_skeleton/task_brief_01.md

Задача: Создай техническое задание в 01_tasks/006_document_skeleton/analysis_01.md
с учетом интерфейсов и модулей из implementation plan.

После завершения сформируй промпт для Developer.
```

---

## Порядок запуска задач

Рекомендуемый порядок (можно запускать параллельно):

1. **Задача 001** (LLM Gateway) - критический путь, начинай первой
2. **Задача 004** (SGR Integration) - можно параллельно с 001, если использовать mock
3. **Задача 006** (Document Skeleton) - зависит от 004

После завершения 001 и 004 можно запускать:
- Задача 002: LLM Gateway: Response Router и Retry
- Задача 003: LLM Gateway: Rate Limit Control
- Задача 005: Unit тесты LLM Gateway

---

## Копируй промпт выше для запуска Analyst
