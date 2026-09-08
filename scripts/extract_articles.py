#!/usr/bin/env python3
"""Extract per-article text from an Economist-style PDF into reader/data/*.js.

Usage:
    python3 scripts/extract_articles.py "PDF/The_Economist_UK_-_22_August_2026.pdf"

Heuristic approach (no embedded PDF bookmarks are present in these issues):
  - The running header at the top of each page ("<page num>The Economist
    <date><Section>" or "<Section><page num>The Economist <date>") tells us
    which section (Britain, Business, ...) a page belongs to.
  - A short text block containing a large font-size span (>=14pt) marks the
    start of a new article; its large-size spans are the title, any smaller
    spans in the same block are the standfirst/kicker.
  - Everything else is treated as body text and appended to the article that
    is currently open.
This is intentionally approximate. Re-run after tweaking the constants below
if a particular issue's articles come out misdetected.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf
from wordfreq import zipf_frequency

REPO_ROOT = Path(__file__).resolve().parent.parent
READER_DATA_DIR = REPO_ROOT / "reader" / "data"
MANIFEST_PATH = READER_DATA_DIR / "manifest.js"

KNOWN_SECTIONS = [
    "The world this week", "Leaders", "Letters", "By Invitation", "Briefing",
    "Britain", "Europe", "United States", "The Americas",
    "Middle East & Africa", "Asia", "China", "International", "Business",
    "Finance & economics", "Science & technology", "Culture",
    "Economic & financial indicators", "Obituary",
]
_SECTION_LOOKUP = {}

HEADER_DATE_RE = re.compile(
    r"The Economist\s+\w+\s+\d{1,2}(?:st|nd|rd|th)\s+\d{4}"
)
# The printed page number as an isolated 1-3 digit run (never part of the
# 4-digit year).
HEADER_PAGENUM_RE = re.compile(r"(?<!\d)\d{1,3}(?!\d)")

TITLE_SIZE_MIN = 14.0
MIN_TITLE_CHARS = 4  # guards against a stray oversized drop-cap character
                      # (1-2 chars) falsely triggering a new article
BODY_SIZE_MIN = 7.0
# Real inter-column gaps on these pages start around 129pt (4-column grid);
# a same-column indented aside can sit ~64pt off its column's left edge. 90
# sits between the two, so indents fold into their column without merging
# genuinely different columns together.
COLUMN_GAP = 90.0

# The Economist's own "end of article" tombstone glyph.
END_MARK = "■"

# Economist named columns: their byline sometimes lands in its own text
# block (falsely triggering a new "article"), and sometimes shares a block
# with the real headline (leaving it stuck as an ugly prefix). Handle both.
KNOWN_COLUMNS = {
    "bagehot", "buttonwood", "bartleby", "chaguan", "ashoka", "lexington",
    "charlemagne", "banyan", "schumpeter", "johnson", "free exchange",
}
COLUMN_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(c) for c in KNOWN_COLUMNS) + r")\s+",
    re.I,
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", " ", text).strip()


def build_section_lookup():
    for name in KNOWN_SECTIONS:
        _SECTION_LOOKUP[normalize(name).lower()] = name
    return _SECTION_LOOKUP


def slugify(text: str) -> str:
    text = normalize(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "untitled"


_GLUE_FIXES = [
    (re.compile(r"([,.;:])([A-Za-z])"), r"\1 \2"),
    (re.compile(r"([”)])([A-Za-z])"), r"\1 \2"),
    (re.compile(r"\b(Mr|Mrs|Ms|Dr)([A-Z])"), r"\1 \2"),
]


def fix_glued_words(text: str) -> str:
    """Some pages in the source PDF have tight kerning that makes PyMuPDF
    drop the space between two words (e.g. 'Kushner,Donald', 'MrKushner').
    These substitutions only fire where a space is provably missing, so
    already-correct text is left untouched."""
    for pattern, repl in _GLUE_FIXES:
        text = pattern.sub(repl, text)
    return text


_WORD_TAIL_RE = re.compile(r"[A-Za-z]+$")
_WORD_HEAD_RE = re.compile(r"^[a-z]+")

# The fragment before the hyphen must itself read as a common, complete word
# (rules out proper nouns and mid-syllable fragments like "de"/"con", which
# only look frequent because they're common short substrings).
REAL_WORD_ZIPF_MIN = 3.5
# The no-hyphen joined form must be (close to) unknown, i.e. not a real
# single English word on its own.
JOINED_WORD_ZIPF_MAX = 0.5


def _looks_like_real_compound(prefix_fragment, suffix_fragment):
    """Decide whether a line-end hyphen is a genuine compound-word hyphen to
    keep (e.g. 'year-' + 'olds' -> 'year-olds') rather than the far more
    common case of a typesetting line-wrap break to remove (e.g. 'de-' +
    'cade' -> 'decade'). See DEVELOPMENT.md for how these thresholds were
    picked and their known false-positive rate."""
    if prefix_fragment[:1].isupper() or len(prefix_fragment) < 3:
        return False
    if zipf_frequency(prefix_fragment.lower(), "en") < REAL_WORD_ZIPF_MIN:
        return False
    joined = (prefix_fragment + suffix_fragment).lower()
    return zipf_frequency(joined, "en") < JOINED_WORD_ZIPF_MAX


def dehyphenate_join(text: str) -> str:
    """Join a block's raw text (with \\n at line wraps) into one paragraph.
    Most line-end hyphens are typesetting artifacts of narrow justified
    columns ('de-\\ncade' -> 'decade') and should be removed, but a line can
    also wrap right on a genuine compound-word hyphen ('year-\\nolds' should
    stay 'year-olds', not become 'yearolds') — see _looks_like_real_compound()."""
    lines = [l for l in text.split("\n") if l.strip()]
    out = ""
    for line in lines:
        line = line.strip()
        if out.endswith("-") and out[-2:-1].isalpha() and line[:1].islower():
            prefix_m = _WORD_TAIL_RE.search(out[:-1])
            suffix_m = _WORD_HEAD_RE.match(line)
            if prefix_m and suffix_m and _looks_like_real_compound(prefix_m.group(), suffix_m.group()):
                out = out + line  # keep the hyphen, just undo the line break
            else:
                out = out[:-1] + line
        elif out:
            out = out + " " + line
        else:
            out = line
    return normalize(out)


def assign_words_to_blocks(dict_blocks, all_words, pad=1.5):
    """Assign each word from page.get_text("words") to exactly one dict
    block, by spatial containment, rather than matching blocks up with a
    block index from a different PyMuPDF extraction call. get_text("dict")
    and get_text("blocks")/get_text("words") each run their own
    block-merging heuristic and can disagree on how many blocks a page has —
    cross-referencing them by index is fragile and can silently drop whole
    blocks (and therefore whole articles) when the counts don't match.
    Bounding-box coordinates, unlike block indices, are consistent across all
    of these calls, so matching by geometry instead is robust regardless of
    how each mode segments blocks.

    A drop-cap's block often overlaps the top of the paragraph block that
    follows it, so a word can fall inside more than one block's (padded)
    box; picking the smallest-area match keeps it out of the much bigger
    paragraph block and avoids double-counting it in both."""
    boxes = [b["bbox"] for b in dict_blocks]
    assigned = [[] for _ in dict_blocks]
    for w in all_words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        best_idx, best_area = None, None
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            if x0 - pad <= cx <= x1 + pad and y0 - pad <= cy <= y1 + pad:
                area = (x1 - x0) * (y1 - y0)
                if best_area is None or area < best_area:
                    best_idx, best_area = i, area
        if best_idx is not None:
            assigned[best_idx].append(w)
    return assigned


def words_to_text(words):
    if not words:
        return ""
    words = sorted(words, key=lambda w: (w[1], w[0]))
    lines = [[words[0]]]
    line_y = words[0][1]
    for w in words[1:]:
        if abs(w[1] - line_y) <= 3.0:
            lines[-1].append(w)
        else:
            lines.append([w])
            line_y = w[1]
    line_texts = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        line_texts.append(" ".join(w[4] for w in line))
    return "\n".join(line_texts)


def block_spans(dict_block):
    spans = []
    for line in dict_block["lines"]:
        for span in line["spans"]:
            spans.append(span)
    return spans


def block_size_stats(dict_block):
    spans = block_spans(dict_block)
    if not spans:
        return 0.0, 0
    max_size = max(s["size"] for s in spans)
    large_chars = sum(len(s["text"]) for s in spans if s["size"] >= TITLE_SIZE_MIN)
    return max_size, large_chars


def looks_like_dek(dict_block):
    """A standfirst/dek is body-sized text, so it can't be told apart from a
    real paragraph by size alone — but unlike body text (set Light, aside
    from the odd raised-caps opening word) a dek block is set almost
    entirely in the SemiBold weight."""
    spans = block_spans(dict_block)
    if not spans:
        return False
    bold_chars = sum(len(s["text"]) for s in spans if "SemiBold" in s["font"] or "Bold" in s["font"])
    total_chars = sum(len(s["text"]) for s in spans)
    return total_chars > 0 and bold_chars / total_chars >= 0.8


def is_banner_block(dict_block):
    """A title / dek / section-label block. These often sit at an x0 that
    doesn't line up with any body column (headlines are frequently centred
    or span multiple columns), so they must be kept out of the column
    clustering below and placed purely by reading (y0) order instead."""
    max_size, large_chars = block_size_stats(dict_block)
    return max_size >= TITLE_SIZE_MIN and large_chars >= MIN_TITLE_CHARS


def classify_header(dict_blocks, block_texts):
    """Return (header_index, section_from_header, page_num) for the running
    header block at the top of the page, or (None, None, None) if not found.

    The header reads "<page><Section>The Economist <date>" on some pages and
    "The Economist <date><Section><page>" on others (the section/page number
    sit on whichever side is the page's outer margin) — word-order isn't
    fixed, so the date phrase and the page number are found independently
    rather than assuming one fixed left-to-right layout."""
    for i, (db, text) in enumerate(zip(dict_blocks, block_texts)):
        if db["bbox"][1] > 40:
            continue
        norm_text = normalize(text)
        date_m = HEADER_DATE_RE.search(norm_text)
        if not date_m:
            continue
        remainder = norm_text[: date_m.start()] + " " + norm_text[date_m.end() :]
        num_m = HEADER_PAGENUM_RE.search(remainder)
        page_num = int(num_m.group()) if num_m else None
        leftover = remainder
        if num_m:
            leftover = remainder[: num_m.start()] + " " + remainder[num_m.end() :]
        section = _SECTION_LOOKUP.get(normalize(leftover).lower())
        return i, section, page_num
    return None, None, None


def order_page_blocks(dict_blocks, block_texts, skip_indices):
    """Reading order for one page: banners (titles/deks/section labels)
    keep their natural top-to-bottom position, while runs of ordinary body
    blocks between banners are sorted left-column-then-right-column. Mixing
    banners into the column clustering itself misplaces them (a headline's
    x0 rarely lines up with a body column) and pushes them to the end of
    whichever column they land in — which then wrongly attaches that
    column's body text to the *previous* article. See scripts README notes
    in extract_articles.py module docstring."""
    items = []
    for i, (db, text) in enumerate(zip(dict_blocks, block_texts)):
        if i in skip_indices:
            continue
        text = text.strip()
        if not text:
            continue
        bbox = db["bbox"]
        if bbox[2] - bbox[0] < 5 and bbox[3] - bbox[1] < 5:
            continue  # tiny corner marker
        y0 = bbox[1]
        max_size, _ = block_size_stats(db)
        if len(text) <= 2 and max_size >= TITLE_SIZE_MIN:
            # A dropped-cap opening letter: PyMuPDF sometimes reports its
            # bbox starting a fraction of a point *below* the paragraph it
            # belongs to (font-metrics quirk), which would otherwise sort
            # the paragraph ahead of its own first letter.
            y0 -= 5.0
        items.append({"db": db, "text": text, "x0": bbox[0], "y0": y0, "banner": is_banner_block(db)})

    items.sort(key=lambda it: it["y0"])

    body_xs = sorted({round(it["x0"]) for it in items if not it["banner"]})
    columns = []
    for x in body_xs:
        if not columns or x - columns[-1][-1] > COLUMN_GAP:
            columns.append([x])
        else:
            columns[-1].append(x)
    col_start = {x: idx for idx, group in enumerate(columns) for x in group}

    def column_of(x0):
        r = round(x0)
        if r in col_start:
            return col_start[r]
        if not col_start:
            return 0
        nearest = min(col_start, key=lambda k: abs(k - r))
        return col_start[nearest]

    result = []
    segment = []

    def flush():
        segment.sort(key=lambda it: (column_of(it["x0"]), it["y0"]))
        result.extend(segment)
        segment.clear()

    for it in items:
        if it["banner"]:
            flush()
            result.append(it)
        else:
            segment.append(it)
    flush()

    return [(it["db"], it["text"]) for it in result]


def new_article(section, page_num):
    return {
        "section": section or "",
        "title": "",
        "dek": "",
        "pageStart": page_num,
        "pageEnd": page_num,
        "paragraphs": [],
    }


def finalize_article(article):
    text_len = sum(len(p) for p in article["paragraphs"])
    if not article["title"] or text_len < 40:
        return None
    return article


def extract(pdf_path: Path):
    build_section_lookup()
    doc = pymupdf.open(pdf_path)

    started = False
    stopped = False
    current_section = ""
    current = None
    pending_dropcap = ""
    awaiting_dek = False
    articles = []

    for pno in range(doc.page_count):
        if stopped:
            break
        page = doc[pno]
        dict_blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
        all_words = page.get_text("words")
        assigned_words = assign_words_to_blocks(dict_blocks, all_words)
        block_texts = [words_to_text(ws) for ws in assigned_words]

        header_idx, header_section, header_page_num = classify_header(dict_blocks, block_texts)
        if header_section:
            current_section = header_section

        skip = {header_idx} if header_idx is not None else set()
        ordered = order_page_blocks(dict_blocks, block_texts, skip)

        page_num_printed = header_page_num if header_page_num is not None else pno + 1

        for db, block_text in ordered:
            spans = block_spans(db)
            if not spans:
                continue
            raw_text = block_text.strip()
            clean_text = dehyphenate_join(raw_text)
            if not clean_text:
                continue

            norm_clean = normalize(clean_text)

            if norm_clean.lower() == "contents":
                started = True
                continue
            if not started:
                continue

            if norm_clean.lower() == "classified":
                stopped = True
                break

            if norm_clean.lower() in KNOWN_COLUMNS:
                continue  # standalone column byline (e.g. "Bagehot"), not an article

            max_size, _ = block_size_stats(db)

            section_match = _SECTION_LOOKUP.get(norm_clean.lower())
            if section_match and max_size >= 15:
                current_section = section_match
                continue

            if is_banner_block(db) and len(norm_clean) > 3:
                finished = finalize_article(current) if current else None
                if finished:
                    articles.append(finished)
                current = new_article(current_section, page_num_printed)
                pending_dropcap = ""
                title_parts, dek_parts = [], []
                for line in db["lines"]:
                    line_text = dehyphenate_join(
                        "".join(s["text"] for s in line["spans"])
                    )
                    if not line_text:
                        continue
                    line_size = max(s["size"] for s in line["spans"])
                    (title_parts if line_size >= TITLE_SIZE_MIN else dek_parts).append(line_text)
                title_text = normalize(" ".join(title_parts))
                title_text = COLUMN_PREFIX_RE.sub("", title_text)
                for name in KNOWN_SECTIONS:
                    if title_text.lower().startswith(name.lower() + " "):
                        current_section = name
                        current["section"] = name
                        title_text = title_text[len(name):].strip()
                        break
                current["title"] = title_text
                current["dek"] = fix_glued_words(normalize(" ".join(dek_parts)))
                awaiting_dek = not current["dek"]
                continue

            if current is None:
                continue
            if max_size < BODY_SIZE_MIN:
                continue
            if len(norm_clean) <= 2:
                # A dropped-cap opening letter (its own oversized block) —
                # stash it and glue it onto the very next paragraph instead
                # of discarding it, so "MOST PEOPLE..." doesn't lose its "M".
                if max_size >= TITLE_SIZE_MIN:
                    pending_dropcap += norm_clean
                continue

            if awaiting_dek and not current["paragraphs"] and looks_like_dek(db):
                current["dek"] = fix_glued_words(norm_clean)
                awaiting_dek = False
                continue
            awaiting_dek = False

            text = pending_dropcap + norm_clean
            pending_dropcap = ""
            ends_article = text.rstrip().endswith(END_MARK)
            if ends_article:
                text = text.rstrip()[: -len(END_MARK)].rstrip()
            current["paragraphs"].append(fix_glued_words(text))
            current["pageEnd"] = page_num_printed
            if ends_article:
                # The Economist prints a "■" tombstone at the true end of
                # many articles (mostly Leaders/columns). Treat it as a hard
                # boundary: finalize now, so no further body text before the
                # next title gets glued onto this now-finished article.
                finished = finalize_article(current)
                if finished:
                    articles.append(finished)
                current = None

    finished = finalize_article(current) if current else None
    if finished:
        articles.append(finished)

    for idx, art in enumerate(articles):
        art["id"] = f"{idx:03d}-{slugify(art['title'])}"

    return articles


def issue_title_from_filename(pdf_path: Path) -> str:
    stem = pdf_path.stem.replace("_", " ")
    return re.sub(r"\s+", " ", stem).strip()


def write_issue_js(slug: str, issue_title: str, articles: list):
    READER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = READER_DATA_DIR / f"{slug}.js"
    payload = {"slug": slug, "title": issue_title, "articles": articles}
    js = (
        "window.ISSUES = window.ISSUES || {};\n"
        f"window.ISSUES[{json.dumps(slug)}] = {json.dumps(payload, ensure_ascii=False, indent=2)};\n"
    )
    out_path.write_text(js, encoding="utf-8")
    return out_path


def update_manifest(slug: str, issue_title: str):
    entries = {}
    if MANIFEST_PATH.exists():
        existing = MANIFEST_PATH.read_text(encoding="utf-8")
        m = re.search(r"window\.ISSUE_MANIFEST\s*=\s*(\[.*\]);", existing, re.S)
        if m:
            try:
                for item in json.loads(m.group(1)):
                    entries[item["slug"]] = item["title"]
            except (json.JSONDecodeError, KeyError):
                pass
    entries[slug] = issue_title
    ordered = [{"slug": s, "title": t} for s, t in entries.items()]
    js = (
        "window.ISSUE_MANIFEST = "
        + json.dumps(ordered, ensure_ascii=False, indent=2)
        + ";\n"
    )
    MANIFEST_PATH.write_text(js, encoding="utf-8")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(sys.argv[1]).resolve()
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    issue_title = issue_title_from_filename(pdf_path)
    slug = slugify(issue_title)

    articles = extract(pdf_path)
    if not articles:
        print("No articles were detected — check the heuristics.", file=sys.stderr)
        sys.exit(1)

    out_path = write_issue_js(slug, issue_title, articles)
    update_manifest(slug, issue_title)

    print(f"Wrote {len(articles)} articles to {out_path}")
    by_section = {}
    for a in articles:
        by_section.setdefault(a["section"] or "(no section)", 0)
        by_section[a["section"] or "(no section)"] += 1
    for section, count in by_section.items():
        print(f"  {section}: {count}")


if __name__ == "__main__":
    main()
