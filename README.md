# English
Learning English through The Economist

## Web reader (one article at a time)

`PDF/` holds the source issues. `reader/` is a self-contained static web app
that lets you browse an issue's contents and open one article at a time
(instead of scrolling through the whole PDF) — handy for using a browser
extension like Kimi to look up words while you read.

### Adding a new issue, step by step

1. Install the extraction dependency once: `pip install -r requirements.txt`
2. **Make sure you're on the right branch** before doing anything else —
   the site only redeploys from pushes to `claude/economist-pdf-web-reader-zn8j39`,
   never from `main`:
   ```
   git checkout claude/economist-pdf-web-reader-zn8j39
   git pull origin claude/economist-pdf-web-reader-zn8j39
   ```
3. Drop the new PDF into `PDF/` (the original file is never modified by the
   script, so it's safe to keep it there permanently).
4. Run the extraction script against that PDF:
   ```
   python3 scripts/extract_articles.py "PDF/The_Economist_UK_-_<new issue>.pdf"
   ```
   This writes `reader/data/<issue-slug>.js` and updates
   `reader/data/manifest.js` (adds the new issue, doesn't touch existing ones).
5. Sanity-check locally if you want, by opening `reader/index.html` straight
   from disk — the new issue should show up on the home page. (Extensions
   like a vocab-lookup helper won't run on this `file://` view, see below.)
6. Commit **both** the new PDF and the generated files, then push **to
   `claude/economist-pdf-web-reader-zn8j39`** — not `main`:
   ```
   git add "PDF/The_Economist_UK_-_<new issue>.pdf" reader/data/manifest.js reader/data/<issue-slug>.js
   git commit -m "Add <new issue> issue"
   git push origin claude/economist-pdf-web-reader-zn8j39
   ```
   Pushing to `main` directly (e.g. from a different local clone, or GitHub's
   web UI) will **not** trigger a redeploy — `.github/workflows/pages.yml`
   only watches the feature branch above.
7. `.github/workflows/pages.yml` republishes `reader/` to GitHub Pages on
   every push to that branch (one-time setup, already done: in the repo's
   Settings → Pages, Source is set to "GitHub Actions"). Wait for the
   workflow to finish (Actions tab), then open the Pages URL in Chrome — the
   new issue appears on the home page; pick it, browse its contents by
   section, click into an article.
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
