# Техническое задание: File Storage - файловое хранилище для скелетов

**Версия:** 01
**Дата:** 2025-01-23
**Задача:** 007_file_storage

---

## 1. Анализ задачи

Задача 007 — реализация персистентности для DocumentSkeleton через file-based JSON. FileStorage обеспечивает сохранение и загрузку результатов обработки документов, избегая дорогой повторной обработки через VLM-OCR.

**Ключевые особенности:**
- File-based JSON выбран как оптимальное решение для v1.0 (10-50 документов)
- Абстракция `Storage` для будущей миграции на БД (ADR-004)
- Конфигурация через environment variables (.env)
- VLM-OCR кэш в отдельной директории с инвалидацией по hash исходного файла

---

## 2. Текущее состояние

**Существующий код:**
- `02_src/document/skeleton.py` — структуры данных DocumentSkeleton, Node, PageRange, InternalStructure, NodeType (задача 006)
- Папка `02_src/storage/` — не существует, нужно создать

**Зависимости:**
- Задача 006: DocumentSkeleton (типы данных для сериализации)
- ADR-004: Стратегия хранения (file-based JSON, структура директорий)

**Библиотеки:**
- `pathlib` (stdlib) — для работы с файловой системой
- `json` (stdlib) — для сериализации
- `typing` (stdlib) — для типов
- `pytest` — для тестов
- `python-dotenv` — для загрузки .env

---

## 3. Предлагаемое решение

### 3.1. Общий подход

**Двухуровневая архитектура:**
1. **Абстрактный базовый класс `Storage`** — интерфейс для всех реализаций
2. **`FileStorage`** — реализация для v1.0 (file-based JSON)

**Конфигурация через .env:**
```bash
STORAGE_BASE_PATH=data/
STORAGE_CACHE_PATH=data/cache/vlm_ocr/
```

**Обработка ошибок:**
- Логирование всех операций чтения/записи
- Проброс исключений (FileNotFoundError, JSONDecodeError) с контекстом
- `load_skeleton` возвращает `None` для несуществующих документов (не exception)

### 3.2. Компоненты

#### Storage (ABC)
- **Назначение:** Абстракция для будущей миграции на БД
- **Интерфейс:**
  - `async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton)`
  - `async def load_skeleton(self, document_id: str) -> Optional[DocumentSkeleton]`
  - `def document_exists(self, document_id: str) -> bool`
- **Зависимости:** `ABC`, `abstractmethod` из `abc`, `DocumentSkeleton` из `document.skeleton`

#### FileStorage (class)
- **Назначение:** File-based JSON хранилище для v1.0
- **Поля:**
  - `base_path: Path` — базовая директория (например `data/`)
- **Конструктор:**
  - Принимает `base_path: str` (или читает из .env)
  - Создает директорию если не существует (`mkdir(parents=True, exist_ok=True)`)
- **Методы:** реализация интерфейса `Storage`

#### Модуль конфигурации (config.py)
- **Назначение:** Загрузка настроек из .env
- **Функции:**
  - `def get_storage_config() -> Dict[str, str]` — возвращает base_path, cache_path

### 3.3. Структуры данных

#### JSON формат skeleton.json
```json
{
  "document_id": "doc_714p",
  "created_at": "2025-01-23T10:00:00Z",
  "source_file": {
    "path": "/path/to/original.pdf",
    "hash": "sha256:abc123...",
    "size_bytes": 5242880
  },
  "nodes": {
    "node_id_1": {
      "id": "section_3",
      "type": "chapter",
      "title": "3. Требования к отчётности",
      "content": "...",
      "page_range": {"start": 15, "end": 42},
      "parent_id": "root",
      "children_ids": ["section_3.1", "section_3.2"],
      "internal_structure": {"raw": {...}},
      "explicit_refs": ["ref:appendix:1"],
      "hash": "a1b2c3d4e5f6",
      "table_data": null
    }
  }
}
```

#### Структура директорий
```
data/
├── {document_id}/
│   └── skeleton.json
└── cache/
    └── vlm_ocr/
        └── {document_id}/
            └── extraction_results.json  (future)
```

### 3.4. Ключевые алгоритмы

#### Сериализация DocumentSkeleton в JSON
1. Получить все узлы через `skeleton._nodes.values()` (доступ к приватному полю)
2. Для каждого узла преобразовать в dict:
   - `page_range` → `{"start": ..., "end": ...}`
   - `internal_structure` → `{"raw": ...}`
   - `type` → `node.type.value` (Enum → string)
3. Собрать в структуру с метаданными (document_id, created_at)
4. Записать в JSON с `ensure_ascii=False, indent=2`

#### Десериализация JSON в DocumentSkeleton
1. Прочитать JSON файл
2. Для каждого node_data:
   - Восстановить `NodeType` из string: `NodeType(node_data["type"])`
   - Восстановить `PageRange` из dict: `PageRange(**node_data["page_range"])`
   - Восстановить `InternalStructure`: `InternalStructure(**node_data["internal_structure"])`
   - Создать `Node` через конструктор
3. Найти корневой узел (где `parent_id is None` или `type == ROOT`)
4. Создать `DocumentSkeleton(document_id, nodes_dict)`

#### Проверка существования документа
```python
def document_exists(self, document_id: str) -> bool:
    return (self.base_path / document_id / "skeleton.json").exists()
```

### 3.5. Изменения в существующем коде

**DocumentSkeleton** — не требует изменений. Используется существующий интерфейс:
- Доступ к `_nodes` (private field) — допустимо для serialization в том же модуле
- Или добавить метод `async def get_all_nodes()` в DocumentSkeleton (если нужно)

---

## 4. План реализации

1. **Создать структуру проекта:**
   - `02_src/storage/__init__.py`
   - `02_src/storage/file_storage.py` — FileStorage класс
   - `02_src/storage/config.py` — конфигурация из .env
   - `02_src/storage/tests/__init__.py`
   - `02_src/storage/tests/test_file_storage.py`
   - `02_src/storage/tests/fixtures/sample_skeleton.json`
   - `.env` (создать пример в проекте)
   - `04_logs/storage/` (папка для логов)

2. **Реализовать конфигурацию (config.py):**
   - Загрузка .env через `python-dotenv`
   - Функция `get_storage_config()`
   - Значения по умолчанию если .env не задан

3. **Реализовать Storage ABC:**
   - Абстрактный базовый класс с методами `save_skeleton`, `load_skeleton`, `document_exists`
   - Типы аргументов и возвращаемых значений

4. **Реализовать FileStorage:**
   - Конструктор с base_path
   - `save_skeleton` — сериализация в JSON
   - `load_skeleton` — десериализация из JSON
   - `document_exists` — проверка файла
   - Обработка ошибок с логированием

5. **Создать fixture sample_skeleton.json:**
   - Пример скелета Положения ЦБ 714-П
   - Root node + 2-3 дочерних узла
   - Один узел с table_data

6. **Реализовать unit тесты:**
   - Тесты сохранения/загрузки
   - Тесты обработки ошибок
   - Тесты document_exists

7. **Добавить логирование:**
   - Логировать все операции save/load
   - Логи в `04_logs/storage/file_storage.log`

---

## 5. Технические критерии приемки

- [ ] TC-001: Storage ABC с абстрактными методами определен
- [ ] TC-002: FileStorage реализует интерфейс Storage
- [ ] TC-003: `save_skeleton` создает `data/{document_id}/skeleton.json`
- [ ] TC-004: `save_skeleton` сериализует все поля Node в JSON
- [ ] TC-005: `load_skeleton` восстанавливает DocumentSkeleton из JSON
- [ ] TC-006: `load_skeleton` возвращает `None` для несуществующего документа
- [ ] TC-007: `document_exists` возвращает `True/False` корректно
- [ ] TC-008: Ошибки чтения/записи логируются и пробрасываются
- [ ] TC-009: JSON формат соответствует ADR-004 (с метаданными)
- [ ] TC-010: Конфигурация через .env работает (base_path)
- [ ] TC-011: Unit тесты покрывают все методы (минимум 80% coverage)
- [ ] TC-012: Fixture sample_skeleton.json валиден и используется в тестах
- [ ] TC-013: Логи пишутся в `04_logs/storage/file_storage.log`

---

## 6. Важные детали для Developer

### Доступ к _nodes DocumentSkeleton
`DocumentSkeleton._nodes` — приватное поле. Два подхода:

**Вариант A:** Прямой доступ (допустимо для serialization в том же модуле):
```python
nodes = skeleton._nodes
```

**Вариант B:** Добавить метод в DocumentSkeleton (более чистый):
```python
# В skeleton.py
async def get_all_nodes(self) -> Dict[str, Node]:
    """Получить все узлы (для сериализации)"""
    return self._nodes.copy()
```

Рекомендую **Вариант B** — более чистый API.

### Обработка Enum при сериализации
`NodeType` — Enum, нужен `.value` для JSON:
```python
"type": node.type.value  # "chapter", "section", etc.
```

При десериализации:
```python
type = NodeType(node_data["type"])
```

### datetime для created_at
Используй `datetime.datetime.now().isoformat()` для created_at в JSON.

### Hash исходного файла (future)
В метаданные `source_file.hash` добавляется в будущих задачах. Для v1.0 можно оставить placeholder:
```json
"source_file": {
  "path": "...",
  "hash": null,
  "size_bytes": 0
}
```

### Кодировка JSON
Используй `encoding='utf-8'` при открытии файлов, `ensure_ascii=False` при json.dump для поддержки кириллицы.

### Создание директорий
Используй `Path.mkdir(parents=True, exist_ok=True)` для создания document_id директории.

### Атомарная запись (опционально)
Для надежности можно использовать temporary file + rename:
```python
temp_path = doc_dir / "skeleton.json.tmp"
with open(temp_path, 'w') as f:
    json.dump(data, f)
temp_path.rename(skeleton_path)
```

### Логирование ошибок
При ошибках чтения/записи логируйте с контекстом:
```python
try:
    with open(path, 'r') as f:
        data = json.load(f)
except FileNotFoundError as e:
    logger.error(f"Skeleton not found for document {document_id}: {e}")
    return None
except json.JSONDecodeError as e:
    logger.error(f"Invalid JSON for document {document_id}: {e}")
    raise
```

### .env файл
Создай `.env.example` в корне проекта:
```bash
STORAGE_BASE_PATH=data/
STORAGE_CACHE_PATH=data/cache/vlm_ocr/
```

Добавь `.env` в `.gitignore`.

### Fixture формат
sample_skeleton.json должен соответствовать формату из раздела 3.3.

### Test.tmp directory
Используй `tmp_path` fixture от pytest для создания временной директории в тестах:
```python
def test_save_load_skeleton(tmp_path):
    storage = FileStorage(base_path=str(tmp_path / "data"))
    # ...
```

---

## 7. Ключевые решения (по требованию из task_brief)

### 7.1. Base путь для хранилища
**Решение:** `data/` по умолчанию, конфигурируется через `STORAGE_BASE_PATH` в .env.

**Обоснование:**
- Соответствует структуре из ADR-004
- Изолирует данные от кода
- Легко мигрировать при изменении структуры

**Альтернативы рассмотрены:**
- Хранение в `02_src/` — смешивание кода и данных (плохая практика)
- Хранение в `03_data/` — возможно, но `data/` ближе к ADR-004

### 7.2. Обработка ошибок чтения/записи
**Решение:** Логировать + пробрасывать исключение с контекстом. `load_skeleton` возвращает `None` для несуществующих документов.

**Обоснование:**
- `None` позволяет вызывающему коду проверить существование без try/except
- Для других ошибок (корrupted JSON, permission denied) — exception лучше
- Логирование необходимо для отладки

**Паттерн:**
```python
# Отсутствие файла → None (нормальное состояние)
if not path.exists():
    return None

# Корrupted JSON → exception (аномальное состояние)
try:
    data = json.load(f)
except json.JSONDecodeError as e:
    logger.error(f"Corrupted skeleton: {e}")
    raise StorageError(f"Invalid JSON for document {document_id}") from e
```

### 7.3. Сжатие JSON для v1.0
**Решение:** Не сжимать. Использовать `indent=2` для читаемости.

**Обоснование:**
- Типичный DocumentSkeleton: 1-5 MB — сжатие не критично
- Читаемость JSON полезна для отладки
- Простота реализации
- Если понадобится — добавить gzip в v2.0

**Альтернативы рассмотрены:**
- `gzip` — добавляет сложность, минимальный выигрыш для 1-5 MB
- `msgpack` — бинарный формат, теряет читаемость

### 7.4. Структура JSON (flat vs nested)
**Решение:** Flat format с метаданными на верхнем уровне.

**Обоснование:**
- Соответствует ADR-004
- Прямое мапинг на `skeleton._nodes`
- Легко расширять метаданными

**Формат:**
```json
{
  "document_id": "...",
  "created_at": "...",
  "nodes": {
    "node_id_1": {...},
    "node_id_2": {...}
  }
}
```

### 7.5. Абстракция Storage
**Решение:** Создать ABC `Storage` с методами `save_skeleton`, `load_skeleton`, `document_exists`.

**Обоснование:**
- Позволит мигрировать на PostgreSQL в v2.0 без изменения контрактов
- Клиентский код использует интерфейс: `storage: Storage = FileStorage()`
- Future: `storage: Storage = PostgreSQLStorage()`

---

## 8. Тестовый план

### Unit тесты (test_file_storage.py)

#### Тесты конфигурации
- `test_get_storage_config_default()` — значения по умолчанию
- `test_get_storage_config_from_env()` — загрузка из .env

#### Тесты FileStorage.save_skeleton
- `test_save_skeleton_creates_directory()` — создается `data/{document_id}/`
- `test_save_skeleton_writes_json()` — создается `skeleton.json`
- `test_save_skeleton_serializes_all_fields()` — все поля Node в JSON
- `test_save_skeleton_with_metadata()` — добавляет created_at
- `test_save_skeleton_overwrites()` — перезапись существующего

#### Тесты FileStorage.load_skeleton
- `test_load_skeleton_restores_document()` — восстанавливает DocumentSkeleton
- `test_load_skeleton_not_exists()` — возвращает None
- `test_load_skeleton_invalid_json()` — выбрасывает exception с логированием
- `test_load_skeleton_all_node_types()` — восстанавливает CHAPTER, SECTION, TABLE, etc.

#### Тесты FileStorage.document_exists
- `test_document_exists_true()` — возвращает True для существующего
- `test_document_exists_false()` — возвращает False для отсутствующего

#### Тесты обработки ошибок
- `test_save_skeleton_permission_denied()` — логирует и пробрасывает exception
- `test_load_skeleton_corrupted_json()` — логирует и выбрасывает StorageError

### Фикстуры для тестов

#### sample_skeleton из JSON
```python
@pytest.fixture
def sample_skeleton_from_json():
    """Загружает sample_skeleton.json и возвращает DocumentSkeleton"""
    with open("fixtures/sample_skeleton.json") as f:
        data = json.load(f)

    nodes = {}
    for node_id, node_data in data["nodes"].items():
        nodes[node_id] = Node(
            id=node_data["id"],
            type=NodeType(node_data["type"]),
            title=node_data["title"],
            content=node_data["content"],
            page_range=PageRange(**node_data["page_range"]),
            parent_id=node_data["parent_id"],
            children_ids=node_data["children_ids"],
            internal_structure=InternalStructure(**node_data["internal_structure"]),
            explicit_refs=node_data["explicit_refs"],
            hash=node_data["hash"],
            table_data=node_data.get("table_data")
        )

    return DocumentSkeleton(
        document_id=data["document_id"],
        nodes=nodes
    )
```

#### tmp storage
```python
@pytest.fixture
def temp_storage(tmp_path):
    """Создает FileStorage с временной директорией"""
    base_path = tmp_path / "data"
    return FileStorage(base_path=str(base_path))
```

---

## 9. Структура проекта для задачи 007

```
02_src/
└── storage/
    ├── __init__.py           # Экспорт Storage, FileStorage, get_storage_config
    ├── file_storage.py       # Storage ABC, FileStorage реализация
    ├── config.py             # Конфигурация из .env
    └── tests/
        ├── __init__.py
        ├── test_file_storage.py  # Unit тесты
        └── fixtures/
            └── sample_skeleton.json

.env.example                 # Пример конфигурации
.env                        # Игнорируется в git (секреты)

04_logs/
└── storage/
    └── file_storage.log    # Логи операций
```

---

## 10. Следующие шаги

После завершения этой задачи:
- Задача 011 (Skeleton Builder) будет использовать FileStorage для сохранения результатов
- Задача 008 (VLM-OCR Extractor) будет использовать кэш директорию для VLM-OCR результатов
- Future: миграция на PostgreSQL при росте требований (>1000 документов)

---

**Готовность к передаче Developer:** Да, ТЗ достаточно детально для middle+ разработчика.
