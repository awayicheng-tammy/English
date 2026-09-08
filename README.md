# English
Learning English through The Economist

## Web reader (one article at a time)

`PDF/` holds the source issues. `reader/` is a self-contained static web app
that lets you browse an issue's contents and open one article at a time
(instead of scrolling through the whole PDF) — handy for using a browser
extension like Kimi to look up words while you read.

1. Install the extraction dependency once: `pip install -r requirements.txt`
2. For each PDF you want to read, run:
   ```
   python3 scripts/extract_articles.py "PDF/The_Economist_UK_-_22_August_2026.pdf"
   ```
   This writes `reader/data/<issue-slug>.js` and updates `reader/data/manifest.js`.
3. Commit and push. `.github/workflows/pages.yml` republishes `reader/` to
   GitHub Pages on every push (one-time setup: in the repo's Settings →
   Pages, set Source to "GitHub Actions"). Open the Pages URL in Chrome —
   pick an issue, browse its contents by section, click into an article.
   (Opening `reader/index.html` straight from disk also works, but Chrome
   blocks browser extensions — like a translation/lookup helper — from
   running on `file://` pages by default, so the Pages URL is the one to
   actually read from.)

The article-splitting is heuristic (font-size based, since these PDFs have
no embedded table of contents), so an occasional title/section may be a
little off — tweak the constants near the top of
`scripts/extract_articles.py` and re-run if you spot something worth fixing.

See [`DEVELOPMENT.md`](DEVELOPMENT.md) for the design notes, the full
debugging history behind each fix, and known remaining issues.
