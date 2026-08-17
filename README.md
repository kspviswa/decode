# Decode

> **Making difficult technical material understandable.**

A **personalized daily news digest** for [Viswa Kumar](https://www.viswakumar.com) — Senior Systems Architect in the telecom field, focused on Private 5G (packet core) and the intersection of network intelligence and AI.

Curated and delivered daily by **Sarathy 🪆** (the assistant).

Each edition is a short, opinionated list of items. Every item has:

- **TLDR** — a few-paragraph summary, enough to decide whether it's worth your time
- **Why read it** — why it matters to this specific reader
- **Link** — to the original article / paper
- **og:image** — the source article's thumbnail where available
- **Categories / tags / source / domain** — driving per-item filters, a topic word cloud, and digest statistics
- **Mermaid diagrams** — optional concept illustrations rendered client-side

Format inspired by [The Daily Diff](https://tdd.cat) (source: [the-daily-diff](https://github.com/arpitbbhayani/the-daily-diff)).

**Site**: <https://decode.viswakumar.com>

## Structure

```
.
├── _quarto.yml            # Quarto website config (logo, theme, mermaid include, output → docs/)
├── _includes/
│   └── mermaid.html       # Loads Mermaid + initializes pre.mermaid → SVG client-side
├── index.qmd              # Home page — title, tagline, edition listing (RSS feed)
├── logo.svg               # Decode logo (signal-bars mark)
├── styles.css             # Digest card / stats / filter / word-cloud styling
└── posts/
    ├── _metadata.yml      # Per-post defaults
    └── YYYY-MM-DD/
        ├── index.qmd      # Day edition page (custom listing)
        ├── digest.ejs.md  # Custom EJS listing template (stats, filters, cards)
        └── stories.yml    # The day's stories — one list entry per story, each
                           # with its own categories, tags, source, domain, link,
                           # og:image, TLDR paragraphs, why, and optional mermaid
```

## Building

```bash
quarto render        # from the project root → builds the site into docs/
```

Quarto ≥ 1.x is required (installed on this host).

## Curation pipeline

A cron job runs daily at 04:00 America/New_York: it collects candidates (HN, arXiv, Reddit RSS, X, aggregators), selects the best 10-11 stories for the reader's interests, writes `stories.yml`, renders, commits, and pushes. Uttaram MCP is the first choice for search and crawl; direct fetch is the fallback.
