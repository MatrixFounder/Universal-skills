Если смотреть шире, то многие знают Jina только как «читалку твитов», но на самом деле это довольно мощный универсальный слой **URL → Markdown для LLM**. ([GitHub][1])

Что она умеет читать:

### 1. Практически любые веб-страницы

```text
https://r.jina.ai/http://example.com
```

* блоги
* документацию
* GitHub Pages
* статьи
* форумы
* Reddit
* X/Twitter
* Hacker News

Jina сама решает, использовать браузер или обычный HTTP-клиент. ([GitHub][1])

---

### 2. GitHub

Особенно полезно для агентов.

```text
https://r.jina.ai/http://github.com/openai/openai-agents-python
```

Можно читать:

* README
* Wiki
* документацию
* GitHub Pages

Для твоего Agentic Development это один из основных кейсов. ([GitHub][1])

---

### 3. PDF

Например:

```text
https://r.jina.ai/http://arxiv.org/pdf/2501.12345.pdf
```

или

```text
https://r.jina.ai/http://example.com/report.pdf
```

PDF автоматически конвертируется в Markdown. ([GitHub][1])

---

### 4. Word / Excel / PowerPoint

Поддерживаются:

* DOCX
* XLSX
* PPTX

Причем можно либо дать URL файла, либо загрузить сам файл через API. ([GitHub][1])

---

### 5. Изображения

Не OCR в чистом виде.

Jina может прогонять картинки через VLM и генерировать текстовое описание:

```http
X-With-Generated-Alt: true
```

После этого агент получает текстовое описание изображения. ([GitHub][1])

---

### 6. Поиск в интернете

Многие не знают про второй сервис:

```text
https://s.jina.ai/berachain ibgt infrared
```

Он:

1. Выполняет поиск.
2. Берет топ результатов.
3. Сам скачивает страницы.
4. Возвращает готовый Markdown.

То есть агенту не нужно отдельно делать Google Search → Fetch URL → Parse HTML. ([GitHub][1])

---

### 7. Скриншоты страниц

Можно получить ссылку на скриншот:

```http
X-Respond-With: screenshot
```

или полный скриншот страницы:

```http
X-Respond-With: pageshot
```

Удобно для агентов, которые анализируют UI. ([GitHub][1])

---

### 8. Извлечение только нужного блока

Например:

```http
X-Target-Selector: article
```

или

```http
X-Target-Selector: .content
```

Можно вытащить только основную статью без меню и рекламы. ([jina.ai][2])

---

### 9. Ссылки и кнопки

Можно попросить сводку всех ссылок на странице:

```http
X-With-Links-Summary: true
```

Для агентов это позволяет строить навигацию по сайту. ([jina.ai][2])

---

### 10. Контент за логином

Можно пробрасывать cookies:

```http
x-set-cookie
```

Поэтому теоретически агент может читать страницы после авторизации (если передать ему куки браузера). ([augmentcode.com][3])

---

Для твоего стека (Claude Code + Obsidian Wiki + агенты) я бы использовал Jina для:

* X/Twitter постов;
* GitHub репозиториев;
* документации библиотек;
* блогов компаний;
* PDF исследований;
* Arxiv статей;
* поиска по интернету через `s.jina.ai`.

По сути это дешевый аналог связки:

```text
Playwright
+ Search API
+ HTML parser
+ Readability
+ PDF parser
```

в одном сервисе. ([GitHub][1])

[1]: https://github.com/jina-ai/reader?utm_source=chatgpt.com "GitHub - jina-ai/reader: Convert any URL to an LLM- ..."
[2]: https://jina.ai/reader/?utm_source=chatgpt.com "Reader API"
[3]: https://www.augmentcode.com/mcp/reader?utm_source=chatgpt.com "Reader MCP by jina-ai | Web Content Grounding"
