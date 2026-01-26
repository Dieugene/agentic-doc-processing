# Decision 002: Мультидокументность (набор файлов как один документ)

**Статус:** Принято
**Дата:** 2025-01-23
**Контекст:** Tech Lead, вопросы по Итерации 2

---

## Контекст

Реальные регламенты состоят из множества файлов:
- Основной документ (PDF)
- Приложение 1 (Excel, лист 1)
- Приложение 2 (Excel, лист 2)
- ...

В архитектуре есть Workspace и Cross-Document Index, но неясно:
1. Является ли набор файлов одним документом или множеством?
2. Как обрабатываются ссылки между файлами?
3. Какой DocumentSkeleton строится?

E2E кейс: большой регламент с Excel-приложениями → BPMN.

---

## Решение

**Каждый файл = отдельный Document**, но с возможностью логической группировки в **DocumentCollection**.

### Модель данных

```python
Document {
  id: string                    // уникальный ID
  file_path: string             // исходный файл
  file_type: enum               // PDF | XLSX | DOCX
  skeleton: DocumentSkeleton    // скелет этого файла
  taxonomy: Taxonomy            // таксономия этого документа
  snapshots: Map<topic_id, SnapshotAgent>
}

DocumentCollection {
  id: string                    // ID коллекции
  name: string                  // "Положение 714-П комплект"
  document_ids: string[]        // входящие документы
  primary_document_id: string   // основной документ (PDF регламента)

  // Метаданные для удобства
  created_at: timestamp
  description: string           // опциональное описание
}
```

### Обработка ссылок между файлами

**Явные ссылки ("см. Приложение 1"):**

1. При построении скелета парсер детектирует ссылки на другие файлы
2. Ссылка резолвится через DocumentCollection:
   - Найти документ с name/title содержащим "Приложение 1"
   - Если найден в этой же collection → internal reference
   - Если нет → external reference (через Cross-Document Index)

**Cross-Document Resolution:**

```
Снэпшот-агент документа А при обработке ссылки:
  1. Проверяет: есть ли referenced документ в той же DocumentCollection?
  2. Если да → запрашивает у снэпшота-агента документа B
  3. Если нет → запрашивает через Cross-Document Index
```

### Навигационный индекс для коллекции

```
CollectionNavigationIndex {
  collection_id: string
  document_indexes: Map<doc_id, NavigationIndex>
  unified_taxonomy: Taxonomy        // объединенная таксономия
  cross_ref_matrix: Map<topic_id, Map<doc_id, Signal>>
}
```

### Агент уровня документа (Document-Level Agent)

Работает на уровне **DocumentCollection**, а не одного документа:

```
DocumentLevelAgent {
  collection_id: string              // работает с коллекцией
  available_documents: Document[]    // все документы коллекции
  available_snapshots: Map<doc_id, Map<topic_id, SnapshotAgent>>

  // Для E2E кейса (регламент → BPMN)
  tools: [
    "query_snapshot",                // запрос к снэпшоту любого документа
    "get_linked_document",           // получить linked document из collection
    "generate_bpmn_xml"
  ]
}
```

---

## Обоснование

1. **Простота:** Один файл = одна единица обработки. Естественное соответствие при парсинге.

2. **Масштабируемость:** Легко добавить новый файл в существующую collection без перестройки всех скелетов.

3. **Соответствие архитектуре:** Cross-Document Index уже предусмотрен для связывания документов.

4. **E2E кейс:** Регламент + Excel приложения = DocumentCollection. Document-Level Agent работает с коллекцией целиком для генерации BPMN.

5. **Гибкость:**
   - Можно загрузить только основной PDF (без приложений)
   - Можно добавить приложения позже
   - Можно создавать cross-collection запросы

---

## Последствия

### Для реализации

- DocumentParser обрабатывает **один файл** → один DocumentSkeleton
- Additional entity: **DocumentCollection** (группировка документов)
- NavigationIndex строится для каждого документа отдельно
- Cross-Document Index становится критически важным

### для用户体验

**Сценарий 1: Загрузка регламента с приложениями**

```bash
# Вариант A: по одному файлу
upload document_714p_main.pdf
upload document_714p_app1.xlsx
upload document_714p_app2.xlsx

# Создать коллекцию
create collection "714-П完整" with documents: [doc1, doc2, doc3]

# Вариант B: ZIP-архив
upload regulation_714p.zip
# → автоматически распаковывается и создается collection
```

**Сценарий 2: Запрос к коллекции**

```
User: "Опиши процесс отчетности согласно Положению 714-П"
→ Document-Level Agent опрашивает снэпшоты всех документов коллекции
→ Включает информацию из Excel приложений
```

### Инвалидация

- При изменении одного файла → инвалидируется только этот Document
- Другие документы в collection не затрагиваются
- Unified taxonomy пересчитывается при изменении любого документа

---

## Связанные решения

- **ADR-001:** Форматы документов (какие файлы поддерживаются)
- **TBD-002:** Мэппинг таксономий при объединении документов
- **TBD-003:** Инвалидация при изменении unified taxonomy

---

## Открытые вопросы

 TBD-002: Как именно мэппить таксономии разных документов при построении unified_taxonomy?
 - Решение: см. TBD-002 в backlog
 - Временное решение: для v1.0 — простое объединение тем, без сложного мэппинга
