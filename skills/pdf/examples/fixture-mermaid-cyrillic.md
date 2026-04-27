# Тестовая диаграмма с кириллицей

Проверяем, что font-fallback chain в `mermaid-config.json` корректно
отображает русские подписи в flowchart и mindmap (без glyphless boxes).

## Flowchart

```mermaid
flowchart LR
    A[Начало] --> B{Условие}
    B -- Да --> C[Обработка]
    B -- Нет --> D[Пропуск]
    C --> E[Конец]
    D --> E
```

## Mindmap

```mermaid
mindmap
  root((Продукт))
    Пользователи
      Регистрация
      Удержание
    Инженерия
      Надёжность
      Производительность
    Бизнес
      Цены
      Рост
```
