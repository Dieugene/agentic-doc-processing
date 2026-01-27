# Будущее решение: Конвертация DOCX/Excel в PDF

**Дата:** 2025-01-26
**Статус:** Отложено до этапа production
**Приоритет:** Medium

## Проблема

Текущая реализация Converter использует fpdf2 для пересоздания PDF из DOCX, что приводит к:
- Потере картинок, диаграмм, графиков
- Потере форматирования таблиц
- Потере специфических шрифтов
- Неподдержке кириллицы (стандартные шрифты fpdf2)

## Анализ альтернатив

### Open-source решения
❌ **python-docx → fpdf2** — текущее решение, теряет контент
❌ **Прямой DOCX → PNG** — не существует open-source библиотеки

### Коммерческие решения (рассмотрены)

#### 1. ConvertAPI
**URL:** https://www.convertapi.com/

**Преимущества:**
- REST API, простой Python SDK
- Поддержка DOCX, XLSX, PPTX → PDF
- Высокое качество конвертации
- Pay-per-use модель

**Недостатки:**
- Требует internet-соединение
- Платный (но есть free tier)

**Пример:**
```python
import convertapi

convertapi.api_secret = 'YOUR_API_KEY'

# DOCX → PDF
result = convertapi.convert('pdf', {
    'File': 'document.docx'
})
result.save('document.pdf')
```

#### 2. GroupDocs.Conversion Cloud
**URL:** https://docs.groupdocs.cloud/conversion/available-sdks/

**Преимущества:**
- Python SDK доступен
- Поддержка множества форматов
- High-fidelity конвертация

**Недостатки:**
- Требует internet
- Платный

### LibreOffice headless (альтернатива)

**Команда:**
```bash
soffice --headless --convert-to pdf document.docx
```

**Преимущества:**
- Бесплатно
- Сохраняет всё (картинки, диаграммы, форматирование)
- Проверенное корпоративное решение

**Недостатки:**
- Требует установки LibreOffice (~500MB)
- Системная зависимость

## Решение для production

**Выбранная стратегия:** Использовать облачный API сервис

**Рекомендация:** ConvertAPI (приоритет) или GroupDocs

**Обоснование:**
1. Нет системных зависимостей (pip install только)
2. Высокое качество конвертации
3. Простая интеграция
4. Масштабируемость

## План реализации (production phase)

1. **Интеграция ConvertAPI:**
   - Создать `02_src/processing/converter_cloud.py`
   - Добавить `CONVERT_API_SECRET` в `.env`
   - Реализовать fallback на локальную конвертацию (если API недоступен)

2. **Интерфейс:**
```python
class CloudConverter:
    async def convert_to_pdf(self, file_path: str, file_type: FileType) -> str:
        """Конвертация через ConvertAPI."""
        pass
```

3. **Fallback стратегия:**
   - Primary: ConvertAPI (cloud)
   - Secondary: LibreOffice (local, если установлен)
   - Tertiary: Текущая реализация (с предупреждением о потерях)

## Текущее ограничение (v1.0)

**Временно:** Поддержка только PDF файлов
- DOCX/Excel конвертация отключена
- Пользователь конвертирует самостоятельно
- Упрощает архитектуру для быстрого MVP

**Когда реализовать:**
- После получения первых результатов с VLM-OCR
- При необходимости production-ready решения
- Когда появятся не-PDF документы

## Зависимости

- Зависит от: Задачи 016-022 (VLM-OCR Infrastructure)
- Блокирует: Полноценную production поддержку DOCX/Excel

## Примечания

- ConvertAPI free tier: 1000 конвертаций/месяц (достаточно для тестов)
- GroupDocs имеет аналогичный free tier
- При превышении quota — fallback на LibreOffice или уведомление пользователя
