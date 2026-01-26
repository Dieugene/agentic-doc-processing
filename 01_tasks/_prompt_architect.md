# Промпт для Architect

Ты - Architect (см. .agents/architect.md).

Прочитай:
- .agents/architect.md
- AGENTS.md
- 00_docs/standards/common/*
- 00_docs/standards/architect/*
- 00_docs/architecture/overview.md
- 00_docs/architecture/_questions_architect.md

Tech Lead обнаружил проблемы при планировании реализации Итерации 2 (Document Skeleton, Document Parser).

Нужны архитектурные решения по:
1. Поддерживаемые форматы документов (PDF, DOCX, Excel, ZIP?)
2. Мультидокументность (набор файлов = один документ или много?)
3. Интеграция VLM-OCR модуля (способ интеграции, границы ответственности)

После принятия решений:
- Обнови или создай необходимые ADR
- Сформируй промпт для возврата Tech Lead

Удали _questions_architect.md после завершения.
