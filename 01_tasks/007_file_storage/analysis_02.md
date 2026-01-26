# Техническое задание: File Storage - файловое хранилище для скелетов

**Версия:** 02
**Дата:** 2025-01-23
**Задача:** 007_file_storage

**Изменения от v01:**
- Обновлено TC-013: логирование на уровне приложения (вместо FileHandler в модуле)
- Добавлено требование запускать тесты и добавлять результаты в implementation_XX.md

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
- `02_src/storage/` — реализована (первая версия)

**Проблемы из review_01.md:**
1. **TC-013 (логирование):** Требовалось "Логи пишутся в `04_logs/storage/file_storage.log`", но модуль использует только `logging.getLogger(__name__)` без FileHandler.
2. **Подтверждение тестов:** Отсутствуют результаты запуска тестов в implementation_01.md.

**Решение по проблеме 1 (TC-013):**
Конфигурация logging handlers (включая FileHandler) должна быть на уровне приложения, а не в отдельных модулях. Модуль `storage` правильно использует только `logger = logging.getLogger(__name__)`. Конфигурация FileHandler для записи в `04_logs/storage/file_storage.log` выносится в:
- `config.py` → функция `setup_logging()` (опционально, для standalone использования)
- ИЛИ в точку входа приложения (recommended для библиотек)

---

## 3. Предлагаемое решение (обновленное)

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
- Логирование всех операций чтения/записи через `logging.getLogger(__name__)`
- Проброс исключений (FileNotFoundError, JSONDecodeError) с контекстом
- `load_skeleton` возвращает `None` для несуществующих документов (не exception)

**Логирование (уточненное):**
- Модуль использует `logger = logging.getLogger(__name__)` для логирования операций
- FileHandler конфигурируется на уровне приложения или через `setup_logging()` в config.py
- **НЕ добавлять FileHandler в __init__ FileStorage** (нарушение best practices для библиотек)

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
- **Логирование:** `logger = logging.getLogger(__name__)` (без FileHandler)

#### Модуль конфигурации (config.py)
- **Назначение:** Загрузка настроек из .env + опциональная настройка logging
- **Функции:**
  - `def get_storage_config() -> Dict[str, str]` — возвращает base_path, cache_path
  - `def setup_logging(log_file: Optional[str] = None) -> None` — опциональная конфигурация FileHandler (для standalone использования)

---

## 4. План реализации (обновленный)

1. **Создать структуру проекта:**
   - `02_src/storage/__init__.py`
   - `02_src/storage/file_storage.py` — FileStorage класс
   - `02_src/storage/config.py` — конфигурация из .env + setup_logging()
   - `02_src/storage/tests/__init__.py`
   - `02_src/storage/tests/test_file_storage.py`
   - `02_src/storage/tests/fixtures/sample_skeleton.json`
   - `.env` (создать пример в проекте)

2. **Реализовать конфигурацию (config.py):**
   - Загрузка .env через `python-dotenv`
   - Функция `get_storage_config()`
   - Функция `setup_logging(log_file: Optional[str] = None)` — опционально
   - Значения по умолчанию если .env не задан

3. **Реализовать Storage ABC:**
   - Абстрактный базовый класс с методами `save_skeleton`, `load_skeleton`, `document_exists`
   - Типы аргументов и возвращаемых значений

4. **Реализовать FileStorage:**
   - Конструктор с base_path
   - `save_skeleton` — сериализация в JSON
   - `load_skeleton` — десериализация из JSON
   - `document_exists` — проверка файла
   - Обработка ошибок с логированием через `logger`
   - **НЕ добавлять FileHandler в __init__**

5. **Создать fixture sample_skeleton.json:**
   - Пример скелета Положения ЦБ 714-П
   - Root node + 2-3 дочерних узла
   - Один узел с table_data

6. **Реализовать unit тесты:**
   - Тесты сохранения/загрузки
   - Тесты обработки ошибок
   - Тесты document_exists

7. **Запустить тесты и добавить результаты в implementation:**
   - Установить зависимости: `pip install -r requirements.txt`
   - Запустить тесты: `pytest 02_src/storage/tests/ -v`
   - Добавить вывод pytest в implementation_XX.md (секция "Результаты тестов")

---

## 5. Технические критерии приемки (обновленные)

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
- [ ] TC-013: Логирование использует `logging.getLogger(__name__)`, FileHandler конфигурируется через `setup_logging()` или на уровне приложения
- [ ] TC-014: Тесты запущены, результаты добавлены в implementation_XX.md

---

## 6. Важные детали для Developer (дополненные)

### Логирование (обновлено)

**Правильный подход для библиотек:**

```python
# В file_storage.py
import logging

logger = logging.getLogger(__name__)

class FileStorage(Storage):
    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton):
        logger.info(f"Saving skeleton for document {document_id}")
        # ... код сохранения
```

**Конфигурация FileHandler (опционально в config.py):**

```python
# В config.py
def setup_logging(log_file: Optional[str] = None):
    """Настраивает FileHandler для логов storage модуля.

    Args:
        log_file: Путь к файлу логов (например '04_logs/storage/file_storage.log')
                   Если None — логи только в stdout.
    """
    logger = logging.getLogger("storage")

    if log_file:
        # Создать директорию если нужно
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        # Добавить FileHandler
        handler = logging.FileHandler(log_file, encoding='utf-8')
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
```

**Использование на уровне приложения:**

```python
# В точке входа приложения
from storage.config import setup_logging

setup_logging(log_file="04_logs/storage/file_storage.log")
```

**ИЛИ через logging.config (recommended):**

```python
# В точке входа приложения
import logging.config

logging.config.dictConfig({
    'version': 1,
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': '04_logs/storage/file_storage.log',
            'formatter': 'default'
        }
    },
    'loggers': {
        'storage': {
            'level': 'INFO',
            'handlers': ['file']
        }
    }
})
```

**Важно:** НЕ конфигурировать handlers в `__init__` FileStorage — это нарушает принцип разделения ответственности и создает проблемы при многопоточном использовании.

### Запуск тестов (новое)

**Обязательно добавить в implementation_XX.md:**

```markdown
## Результаты тестов

### Установка зависимостей
```bash
pip install -r requirements.txt
```

### Запуск тестов
```bash
pytest 02_src/storage/tests/ -v
```

### Вывод pytest
```
========================= test session starts ==========================
collected 13 items

test_file_storage.py::test_save_skeleton_creates_directory PASSED
test_file_storage.py::test_save_skeleton_writes_json PASSED
...
========================= 13 passed in 0.45s ==========================
```

### Покрытие кода
```bash
pytest 02_src/storage/tests/ --cov=storage --cov-report=term-missing
```

```
Name                      Stmts   Miss  Cover   Missing
-------------------------------------------------------
storage/__init__.py           2      0   100%
storage/config.py            15      1    93%   23
storage/file_storage.py     112      8    93%   145-152
-------------------------------------------------------
TOTAL                       129      9    93%
```
```

### Остальные детали (без изменений из v01)

*Доступ к _nodes DocumentSkeleton, обработка Enum, datetime, JSON кодировка, атомарная запись, .env файл, fixtures — см. analysis_01.md разделы 6-10.*

---

## 7. Ключевые решения (обновленные)

### 7.1. Логирование в файл (TC-013) - **ИЗМЕНЕНО**

**Решение:** Модуль `storage` использует только `logging.getLogger(__name__)`. FileHandler конфигурируется через `setup_logging()` в config.py (для standalone) или на уровне приложения (recommended).

**Обоснование:**
- **Best practice для библиотек:** модули не должны конфигурировать logging handlers
- **Проблема FileHandler в __init__:**
  - Создает multiple handlers при повторном импорте
  - Проблемы с многопоточностью
  - Модуль становится менее reusable (зашивает путь к файлу логов)
- **Правильный подход:**
  - Модуль логирует через `logger = logging.getLogger(__name__)`
  - Приложение конфигурирует куда писать (stdout, file, и т.д.)
  - Опционально: `setup_logging()` для удобства standalone использования

**Альтернативы рассмотрены:**
- FileHandler в `__init__` FileStorage — ❌ нарушает best practices
- FileHandler через `setup_logging()` — ✅ для convenience
- Конфигурация на уровне приложения — ✅ recommended

**Результат:** TC-013 обновлен — логирование через `getLogger()`, FileHandler опционально через `setup_logging()`.

### 7.2. Запуск тестов и результаты - **НОВОЕ**

**Решение:** Developer должен запускать тесты и добавлять результаты в implementation_XX.md.

**Обоснование:**
- Подтверждение что код работает
- Доказательство coverage
- Базовая линия для будущих изменений (regression testing)

**Процесс:**
1. Установить зависимости из requirements.txt
2. Запустить `pytest 02_src/storage/tests/ -v`
3. Скопировать вывод в implementation_XX.md (секция "Результаты тестов")
4. (Опционально) Запустить с coverage: `--cov=storage --cov-report=term-missing`

*Остальные решения (7.2-7.5 из v01) без изменений: Base путь, Обработка ошибок, Сжатие JSON, Структура JSON, Абстракция Storage.*

---

## 8. Тестовый план (без изменений из v01)

*Unit тесты и фикстуры — см. analysis_01.md раздел 8.*

---

## 9. Структура проекта (без изменений из v01)

```
02_src/
└── storage/
    ├── __init__.py           # Экспорт Storage, FileStorage, get_storage_config
    ├── file_storage.py       # Storage ABC, FileStorage реализация
    ├── config.py             # Конфигурация из .env + setup_logging()
    └── tests/
        ├── __init__.py
        ├── test_file_storage.py  # Unit тесты
        └── fixtures/
            └── sample_skeleton.json

.env.example                 # Пример конфигурации
.env                        # Игнорируется в git (секреты)
```

---

## 10. Следующие шаги

После завершения этой задачи:
- Задача 011 (Skeleton Builder) будет использовать FileStorage для сохранения результатов
- Задача 008 (VLM-OCR Extractor) будет использовать кэш директорию для VLM-OCR результатов
- Future: миграция на PostgreSQL при росте требований (>1000 документов)

---

**Готовность к передаче Developer:** Да, ТЗ достаточно детально для middle+ разработчика.
