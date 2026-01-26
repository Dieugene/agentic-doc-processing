# Decision 004: Стратегия хранения данных для v1.0

**Статус:** Принято
**Дата:** 2025-01-23
**Контекст:** Tech Lead, вопросы по Итерации 2 (задача 007)

---

## Контекст

В рамках Итерации 2 требуется персистентность результатов обработки документов:
- DocumentSkeleton (структура документа)
- NavigationIndex (навигационный индекс)
- Taxonomy (таксономия)
- SnapshotAgents (снэпшоты)

Задача 007 (FileStorage) блокирует задачи 011-012. Требуется выбрать стратегию хранения для v1.0.

---

## Решение

**File-based JSON для v1.0 с абстракцией для будущей миграции.**

### Выбор: Вариант A (File-based JSON)

```
data/
├── {document_id}/
│   ├── skeleton.json              # DocumentSkeleton
│   ├── navigation_index.json      # NavigationIndex (будущая задача)
│   ├── taxonomy.json              # Taxonomy (будущая задача)
│   └── snapshots/                 # SnapshotAgents
│       ├── {topic_id}_agent.json
│       └── ...
├── cache/
│   └── vlm_ocr/                   # Кэш VLM-OCR ответов
│       └── {document_id}/
│           └── pages/             # PNG страницы (опционально)
└── config/
    └── storage_config.json        # Конфигурация хранилища
```

### Обоснование выбора

| Критерий | v1.0 требования | File-based JSON | PostgreSQL / MongoDB |
|----------|----------------|-----------------|----------------------|
| **Количество документов** | 10-50 | ✅ Достаточно | Overkill |
| **Разрмер данных** | 50-500 MB | ✅ Достаточно | Overkill |
| **Сложные запросы** | Не нужны | ✅ Достаточно | Избыточно |
| **Конкурентный доступ** | Не нужен | ✅ Достаточно | Избыточно |
| **Зависимости** | Минимум | ✅ Нет | Доп. инфраструктура |
| **Скорость разработки** | PoC | ✅ Быстро | Медленнее |
| **Деплой** | Локальный | ✅ Тривиально | Сложнее |

**Вывод:** File-based JSON оптимален для v1.0 (PoC + интеграционные тесты).

---

## Структура хранения

### DocumentSkeleton

```json
// data/{document_id}/skeleton.json
{
  "document_id": "doc_714p",
  "created_at": "2025-01-23T10:00:00Z",
  "source_file": {
    "path": "/path/to/original.pdf",
    "hash": "sha256:abc123...",
    "size_bytes": 5242880
  },
  "nodes": {
    "root": {
      "id": "root",
      "type": "root",
      "title": "Положение 714-П",
      "content": "...",
      "page_range": {"start": 1, "end": 150},
      "parent_id": null,
      "children_ids": ["section_1", "section_2"],
      "internal_structure": {...},
      "explicit_refs": [],
      "hash": "node_hash_1"
    },
    "section_1": {...}
  }
}
```

### NavigationIndex (будущая задача)

```json
// data/{document_id}/navigation_index.json
{
  "document_id": "doc_714p",
  "taxonomy_version": "v1",
  "matrix": {
    "section_1": {
      "topic_reporting_deadlines": {
        "content_description": "Раздел устанавливает сроки...",
        "sub_references": ["1.2", "1.2.1"]
      }
    }
  }
}
```

### SnapshotAgent (будущая задача)

```json
// data/{document_id}/snapshots/{topic_id}_agent.json
{
  "id": "snapshot_reporting_deadlines_doc714p",
  "document_id": "doc_714p",
  "topic_id": "reporting_deadlines",
  "system_prompt": "...",
  "context": {
    "summary": "...",
    "source_nodes": ["section_3", "appendix_1"],
    "scope_description": "..."
  },
  "created_at": "2025-01-23T10:00:00Z",
  "status": "active"
}
```

---

## Кэширование VLM-OCR результатов

### Проблема

VLM-OCR вычислительно дорогой. Необходимо кэшировать:
1. PNG после рендеринга (если не в памяти)
2. VLM-OCR ответы (текст, структура, таблицы)

### Решение: отдельный кэш-директорий

```
data/cache/vlm_ocr/{document_id}/
├── pages/                          # PNG страницы (опционально)
│   ├── page_001.png
│   ├── page_002.png
│   └── ...
└── extraction_results.json        # VLM-OCR ответы
```

**extraction_results.json:**

```json
{
  "document_id": "doc_714p",
  "source_hash": "sha256:abc123...",
  "extracted_at": "2025-01-23T10:00:00Z",
  "results": {
    "text": "полный текст...",
    "structure": {...},
    "tables": [...]
  }
}
```

### Инвалидация кэша

**При изменении исходного файла:**

```python
def should_reextract(document_id: str, source_file: str) -> bool:
    """Проверить нужно ли перерабатывать через VLM-OCR"""
    cache_path = get_cache_path(document_id)
    if not cache_path.exists():
        return True

    cached = load_cached_result(document_id)
    current_hash = calculate_file_hash(source_file)

    return cached["source_hash"] != current_hash
```

---

## Абстракция для будущей миграции

### Интерфейс Storage (общий для всех реализаций)

```python
from abc import ABC, abstractmethod
from typing import Optional

class Storage(ABC):
    """Абстракция для персистентности. Позволит мигрировать на БД в v2.0."""

    @abstractmethod
    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton):
        """Сохранить скелет"""
        pass

    @abstractmethod
    async def load_skeleton(self, document_id: str) -> Optional[DocumentSkeleton]:
        """Загрузить скелет"""
        pass

    @abstractmethod
    def document_exists(self, document_id: str) -> bool:
        """Проверить существование"""
        pass
```

### FileStorage (реализация для v1.0)

```python
class FileStorage(Storage):
    """Файловое хранилище - реализация для v1.0"""

    def __init__(self, base_path: str = "data/"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton):
        """Сохранить в JSON"""
        # Реализация...
        pass

    async def load_skeleton(self, document_id: str) -> Optional[DocumentSkeleton]:
        """Загрузить из JSON"""
        # Реализация...
        pass

    def document_exists(self, document_id: str) -> bool:
        """Проверить существование файла"""
        return (self.base_path / document_id / "skeleton.json").exists()
```

### Миграция на БД в v2.0

```python
# v2.0: PostgreSQL реализация
class PostgreSQLStorage(Storage):
    """БД хранилище - реализация для v2.0"""

    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)

    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton):
        """Сохранить в PostgreSQL"""
        # SQL INSERT...
        pass

# Клиентский код не меняется!
storage: Storage = FileStorage()  # v1.0
storage: Storage = PostgreSQLStorage()  # v2.0
```

---

## Ответы на вопросы Tech Lead

### 1. Ожидаемое количество документов

**v1.0:** 10-50 документов (достаточно для PoC и интеграционных тестов)

**File-based JSON выдерживает:**
- До 1000 документов без проблем
- При 1000+ может потребоваться БД для скорости запросов

### 2. Размер DocumentSkeleton

**Оценка:**
- Нормативный акт 100-200 страниц → 1-5 MB JSON
- С большим количеством таблиц → до 10 MB

**File-based JSON выдерживает:**
- 50 документов × 5 MB = 250 MB — тривиально
- Даже 1000 документов = 5 GB — приемлемо для локального хранилища

### 3. Нужны ли сложные запросы

**v1.0:** Нет. Основные операции:
- Загрузка по ID
- Проверка существования
- Список всех документов (простой glob)

**File-based JSON достаточен.**

### 4. Конкурентный доступ

**v1.0:** Не нужен (один пользователь, последовательная обработка)

**v2.0:** При необходимости — миграция на PostgreSQL.

---

## Последствия

### Для реализации

- **Задача 007:** FileStorage реализуется как в task_brief_01.md
- **Интерфейс Storage:** добавляется абстракция для будущей миграции
- **VLM-OCR кэш:** добавляется отдельная директория `data/cache/vlm_ocr/`

### Для архитектуры

- v1.0: File-based JSON
- v2.0: Подготовка к миграции на PostgreSQL при росте (>1000 документов)
- Абстракция Storage позволяет сменить реализацию без изменения контрактов

### Ограничения

- Нет транзакционности (для v1.0 не нужно)
- Нет сложных запросов (для v1.0 не нужно)
- Потенциальные race conditions при конкурентной записи (для v1.0 не актуально)

---

## Планы на v2.0

При росте требований (>1000 документов, конкурентный доступ):

1. **Миграция на PostgreSQL:**
   - Таблицы: documents, nodes, navigation_index, taxonomy, snapshots
   - Индексы для быстрых запросов
   - Транзакционность

2. **Процедура миграции:**
   - Скрипт миграции `migrate_to_db.py`
   - Читает все JSON → импортирует в PostgreSQL
   - Верификация данных

3. **Обратная совместимость:**
   - Экспорт из БД в JSON (для резервирования)
   - Двойная запись некоторое время (transition period)

---

## Связанные решения

- **ADR-001:** Форматы документов (источник файлов для кэширования)
- **Задача 007:** FileStorage реализация (task_brief_01.md)
- **Задача 011:** Skeleton Builder (использует FileStorage)
