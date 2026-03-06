---
name: supadata-intel
description: >
  YouTube transcription, video intelligence, competitor monitoring, and web research using Supadata API.
  Use this skill whenever an agent needs to: transcribe a YouTube video, analyze competitor content on YouTube,
  monitor industry channels, extract insights from video content, research prospects via their YouTube/social presence,
  scrape competitor websites, or gather market intelligence from video platforms.
  GrowthLab, KnowledgeKeeper, and CopyAgent should all use this skill proactively.
---

# Supadata Intelligence Skill

Supadata API umožňuje agentům "vidět" a "slyšet" internet — YouTube videa, sociální sítě, weby.
Tohle je náš oči a uši pro competitive intelligence a content research.

## API přístup

```
Base URL: https://api.supadata.ai/v1
Header: x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f
```

## Co umíme

### 1. Přepis videa (YouTube, TikTok, Instagram, X, Facebook)

```bash
# Jednoduchý přepis jako text
curl -X GET "https://api.supadata.ai/v1/transcript?url=YOUTUBE_URL&text=true" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"

# S timestampy (pro analýzu)
curl -X GET "https://api.supadata.ai/v1/transcript?url=YOUTUBE_URL&text=false" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"

# Specifický jazyk
curl -X GET "https://api.supadata.ai/v1/transcript?url=YOUTUBE_URL&lang=cs&mode=auto" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"
```

**Parametry:**
- `url` — URL videa (povinné)
- `text` — `true` pro plain text, `false` pro timestamped chunky
- `lang` — ISO 639-1 kód jazyka (cs, en, de...)
- `mode` — `native` (existující titulky), `generate` (AI přepis), `auto` (zkusí titulky, fallback na AI)
- `chunkSize` — max znaků na chunk

**Async pro videa 20+ min:** Vrátí HTTP 202 s `jobId`. Polluj `/v1/transcript/{jobId}` každou sekundu.

### 2. Metadata videa/kanálu

```bash
# Metadata videa (views, likes, author, tags...)
curl -X GET "https://api.supadata.ai/v1/metadata?url=YOUTUBE_URL" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"

# Info o kanálu
curl -X GET "https://api.supadata.ai/v1/youtube/channel?id=CHANNEL_ID" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"

# Videa z kanálu
curl -X GET "https://api.supadata.ai/v1/youtube/channel/videos?id=CHANNEL_ID" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"
```

### 3. YouTube Search

```bash
curl -X GET "https://api.supadata.ai/v1/youtube/search?query=HR+engagement+tools+czech&type=video&sortBy=date&limit=20" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"
```

**Filtry:** `type` (video/channel/playlist), `uploadDate` (hour/today/week/month/year), `duration` (short/medium/long), `sortBy` (relevance/rating/date/views), `features` (hd/subtitles/live/4k)

### 4. AI Structured Extraction

```bash
# Extrahuj strukturovaná data z videa pomocí AI
curl -X POST "https://api.supadata.ai/v1/extract" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "YOUTUBE_URL",
    "prompt": "Extract all mentioned company names, their products, and any pricing information",
    "schema": {
      "type": "object",
      "properties": {
        "companies": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "products": {"type": "array", "items": {"type": "string"}},
              "pricing": {"type": "string"}
            }
          }
        }
      }
    }
  }'
```

Vždycky async — vrátí `jobId`, polluj `/v1/extract/{jobId}`.

### 5. Web Scraping

```bash
# Scrapni jednu stránku (vrátí markdown)
curl -X GET "https://api.supadata.ai/v1/web/scrape?url=https://competitor.com/pricing" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"

# Crawluj celý web (async)
curl -X POST "https://api.supadata.ai/v1/web/crawl" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://competitor.com", "limit": 50}'

# Mapa všech URL na webu
curl -X GET "https://api.supadata.ai/v1/web/map?url=https://competitor.com" \
  -H "x-api-key: sd_72aa5ed2104bfeccb0177afb207d395f"
```

## Kredity a limity

- Native přepis: 1 kredit
- AI přepis: 2 kredity/min videa
- Metadata: 1 kredit
- YouTube search: 1 kredit/stránka
- Web scrape: 1 kredit/stránka
- Web crawl: 1 kredit/stránka
- AI extract: 5+ kreditů

Pouze veřejně dostupný obsah. Max 1 GB pro soubory. Videos 20+ min jsou async.

---

## Použití v agentním systému

### GrowthLab — Competitive Intelligence

Každý den:
1. Prohledej YouTube pro nová videa o HR tech, employee engagement, Czech HR market
2. Přepiš top 3 videa a extrahuj klíčové insights
3. Zapiš do `knowledge/DAILY-INTEL.md`

Každý týden:
1. Scrape pricing stránky top 5 konkurentů
2. Porovnej s minulým týdnem
3. Zapiš změny do `knowledge/COMPETITOR_WATCH.md`

### KnowledgeKeeper — Content Intelligence

Když Josef sdílí YouTube link:
1. Přepiš video
2. Extrahuj klíčové body, citáty, data
3. Zapiš do příslušného knowledge souboru
4. Navrhni jak to využít v sales/content

### CopyAgent — Research pro content

Před psaním blogu/emailu:
1. Najdi relevantní videa na téma
2. Přepiš a extrahuj unikátní insights
3. Použij jako podklady pro originální obsah

### DealOps — Prospect Research

Před schůzkou:
1. Najdi YouTube/social přítomnost prospekta
2. Přepiš jejich poslední videa/rozhovory
3. Extrahuj témata, bolesti, priority
4. Přidej do SPIN prep dokumentu
