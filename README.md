# English
Learning English through The Economist

## Web reader (one article at a time)

`reader/` is a self-contained static web app that lets you browse an
issue's contents and open one article at a time (instead of scrolling
through the whole PDF) — handy for using a browser extension like Kimi to
look up words while you read. It's published to
https://awayicheng-tammy.github.io/English/ from the
`claude/economist-pdf-web-reader-zn8j39` branch (pushes to `main` don't
redeploy it).

### Adding a new issue

**Step-by-step checklist: [`操作清单.md`](操作清单.md).** In short:

1. Get the latest `scripts/extract_articles.py` and run
   `pip install -r requirements.txt`.
2. Put the PDF in your local `PDF/` folder. PDFs stay local — they're too
   big for GitHub and the site doesn't need them (`PDF/*.pdf` is
   git-ignored).
3. `python3 scripts/extract_articles.py "PDF/The_Economist_UK_-_<date>.pdf"`
   writes `reader/data/<issue-slug>.js` and updates `reader/data/manifest.js`.
4. Upload just those two files to `reader/data/` on the
   `claude/economist-pdf-web-reader-zn8j39` branch. The Pages workflow
   redeploys the site.

When the script gets a fix, previously uploaded issues only pick it up once
they're re-extracted locally (same PDF filename, so the issue is
overwritten rather than duplicated) and re-uploaded — see part B of the
checklist.

The article-splitting is heuristic (font-size based, since these PDFs have
no embedded table of contents), so an occasional title/section may be a
little off — tweak the constants near the top of
`scripts/extract_articles.py` and re-run if you spot something worth fixing.

See [`DEVELOPMENT.md`](DEVELOPMENT.md) for the design notes, the full
debugging history behind each fix, and known remaining issues.
