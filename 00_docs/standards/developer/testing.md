# Стандарты для Developer: Запуск тестов

## pytest configuration

Все артефакты тестов должны находиться в `04_logs/`:

**HTML coverage отчеты:** `04_logs/htmlcov/`
**Coverage data:** `.coverage` (в корне, для инструментов)

## Правильная команда запуска тестов

```bash
pytest --cov=02_src --cov-report=html:04_logs/htmlcov --cov-report=term-missing
```

## Что НЕ делать

❌ **НЕ создавать** артефакты в корне проекта:
- `htmlcov/` в корне — НЕПРАВИЛЬНО
- Использовать `--cov-report=html` (создает htmlcov/ в корне)

✅ **ПРАВИЛЬНО:**
```bash
pytest --cov-report=html:04_logs/htmlcov
```

## pytest.ini

В проекте создан `pytest.ini` с правильной конфигурацией:

```ini
[tool:pytest]
addopts =
    --cov-report=html:04_logs/htmlcov
    --cov-report=term-missing
```

Все тесты запускаются через `pytest` (без опций) используют эту конфигурацию.

## .gitignore

Артефакты тестов добавлены в `.gitignore`:
```
# Testing
htmlcov/
.coverage
.coverage.*
.pytest_cache/
04_logs/htmlcov/
```

## После запуска тестов

**Если создался `htmlcov/` в корне** — это ошибка:
1. Удалить: `rm -rf htmlcov/`
2. Проверить pytest.ini
3. Использовать правильную команду

## Reference

- pytest.ini: в корне проекта
- Стандарты: `00_docs/standards/common/structure.md`
- Testing artifacts: должны быть в `04_logs/`
