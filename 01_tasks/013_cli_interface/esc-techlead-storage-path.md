# Эскалация: Нарушение ADR 004 - путь к хранилищу

**Дата:** 2025-01-26
**От:** Reviewer (Agent)
**Контекст:** Review задачи 013 (CLI Interface)

## Нарушение

**Что:** Task brief 013 и реализация CLI используют путь `04_storage/skeletons` вместо `data/` из ADR 004

**ADR 004** (строки 27-42):
```
data/
├── {document_id}/
│   ├── skeleton.json
├── cache/
│   └── vlm_ocr/
```

**Task brief 013** (строки 66-68, 103, 217):
```
04_storage/
└── skeletons/
    └── <document_id>.json
```

## Где смотреть

**ADR:**
- `00_docs/architecture/decision_004_storage_strategy.md` (строки 27-42, 217-234)

**Task brief:**
- `01_tasks/013_cli_interface/task_brief_01.md` (строки 66-68, 103, 217)
- AC-003: `04_storage/skeletons/<document_id>.json`

**Реализация:**
- `02_src/processing/cli.py:50` - `default="04_storage/skeletons"`
- `02_src/processing/cli.py:95` - вывод с `.json/skeleton.json`

## Почему это проблема

1. **Нарушение архитектурного решения** - ADR 004 принят Tech Lead, но не соблюдается
2. **Отсутствует ссылка на ADR** - task brief не объясняет отклонение от стандарта
3. **Несогласованность** - `config.py` использует `data/`, CLI использует `04_storage/skeletons`
4. **Технический долг** - создана директория `04_storage/`, которой не должно быть

## Что нужно от Tech Lead

1. Определить правильный путь: `data/` (по ADR 004) или `04_storage/skeletons` (фактически)
2. Если `04_storage/skeletons` - создать ADR с изменением решения
3. Обновить backlog: задача на исправление несоответствия
4. Решить: удалять ли `04_storage/` или мигрировать на неё
