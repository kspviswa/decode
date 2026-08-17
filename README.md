# Decode

> **Making difficult technical material understandable.**

A **personalized daily news digest** for [Viswa Kumar](https://www.viswakumar.com) — Senior Systems Architect in the telecom field, focused on Private 5G (packet core) and the intersection of network intelligence and AI.

Each edition is a short, opinionated list of items. Every item has:

- **TLDR** — what it says, in one or two sentences
- **Why read it** — why it matters to this specific reader
- **Link** — to the original article / paper

Format inspired by [The Daily Diff](https://tdd.cat) (source: [the-daily-diff](https://github.com/arpitbbhayani/the-daily-diff)).

Curated and delivered daily by [Sarathy 🪆](https://github.com/kspviswa/sarathy).

## Structure

```
.
├── _quarto.yml            # Quarto website config (sketchy theme, output → docs/)
├── index.qmd              # Home page — title, tagline, edition listing (RSS feed)
├── about.qmd              # About — who reads this, what Decode is
├── styles.css             # Digest card styling
├── profile.jpg            # Portrait (placeholder — swap for a real photo)
└── posts/
    ├── _metadata.yml      # Per-post defaults
    └── YYYY-MM-DD/
        └── index.qmd      # One digest edition per day
```

## Building

```bash
quarto render        # from the project root → builds the site into docs/
```

Quarto ≥ 1.x is required (installed on this host).

## Deploying (TBD)

- **Option A — GitHub Pages**: serve `docs/` from the `main` branch (or a `gh-pages` branch).
- **Option B — Cloudflare Pages**: build command `quarto render`, output directory `docs`.

The `site-url` in `_quarto.yml` should be updated to match whichever host is chosen (affects RSS feed URLs).

## Status

- [x] Scaffold with Sketchy theme, tagline, and digest styling
- [x] Sample date-ordered editions (placeholder content, all links verified)
- [ ] Daily curation pipeline (source selection → TLDR → edition commit)
- [ ] Delivery schedule
- [ ] Deploy target (GitHub Pages vs Cloudflare)
