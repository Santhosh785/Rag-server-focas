"""
ingest.py — Production PDF ingestion pipeline for math/formula-heavy study material.

Fixes over v2:
  1. Correct fraction detection: requires math unicode + denominator narrower than page width
  2. Fixes false positive: header + first prose line no longer merged
  3. Fixes false positive: full-width prose lines (Based on / of T Ltd.) no longer merged
  4. Fixes denominator-only orphans (lone "12", "100", "25" under a calc line)
  5. Fixes answer_text empty: ANSWER: marker is now correctly preserved in extracted text
  6. Fixes sentence split by table: prose ordering fixed

Usage:
    python ingest.py --pdf_dir ./pdfs
    python ingest.py --pdf_dir ./pdfs --verbose
"""

import os
import re
import argparse
import logging
import json
from collections import defaultdict
from datetime import datetime, timezone

import pdfplumber
import base64
from io import BytesIO
from PIL import Image
try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

from openai import OpenAI
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

MONGODB_URI = os.environ.get("MONGODB_URI")
OPENAI_KEY  = os.environ.get("OPENAI_API_KEY")
if not MONGODB_URI:
    raise SystemExit("❌  MONGODB_URI not set in .env")
if not OPENAI_KEY:
    raise SystemExit("❌  OPENAI_API_KEY not set in .env")

DB_NAME     = "exam_db"
COLLECTION  = "questions"
EMBED_MODEL = "text-embedding-3-small"
VISION_MODEL = "gpt-4o" # Switched to full gpt-4o for high-fidelity extraction as mini was truncating long answers.

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

INGESTED_TRACKER_DIR = "ingestion_status"

def get_ingested_files(subject: str = None):
    """Retrieve set of ingested filenames for a specific subject from its JSON tracker."""
    if not subject:
        # Fallback for general or unknown subjects
        tracker = "ingested_files.json"
    else:
        tracker = os.path.join(INGESTED_TRACKER_DIR, f"{subject}.json")

    if os.path.exists(tracker):
        try:
            with open(tracker, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()

def save_ingested_file(filename: str, subject: str):
    """Save a filename to the subject-specific JSON tracker."""
    ingested = list(get_ingested_files(subject))
    if filename not in ingested:
        ingested.append(filename)
        os.makedirs(INGESTED_TRACKER_DIR, exist_ok=True)
        tracker = os.path.join(INGESTED_TRACKER_DIR, f"{subject or 'unknown'}.json")
        with open(tracker, "w") as f:
            json.dump(ingested, f, indent=4)

# ── Math Unicode → ASCII ───────────────────────────────────────────────────────

_MATH_RANGES = [
    (0x1D400, 0x1D419, ord('A')),   # Math Bold Uppercase A–Z
    (0x1D41A, 0x1D433, ord('a')),   # Math Bold Lowercase a–z
    (0x1D434, 0x1D44D, ord('A')),   # Math Italic Uppercase A–Z
    (0x1D44E, 0x1D467, ord('a')),   # Math Italic Lowercase a–z
    (0x1D468, 0x1D481, ord('A')),   # Math Bold Italic Uppercase A–Z
    (0x1D482, 0x1D49B, ord('a')),   # Math Bold Italic Lowercase a–z
]

_MATH_SPECIAL = {
    0x1D455: 'h',
    0x210E:  'h',
    0x2113:  'l',
    0x212F:  'e',
    0x2134:  'o',
}

def normalize_math_unicode(text: str) -> str:
    """
    Convert Unicode math italic/bold characters to plain ASCII.
    𝐹𝑖𝑥𝑒𝑑 𝐴𝑠𝑠𝑒𝑡𝑠 → Fixed Assets
    𝐶𝑢𝑟𝑟𝑒𝑛𝑡 𝐿𝑖𝑎𝑏𝑖𝑙𝑖𝑡𝑖𝑒𝑠 → Current Liabilities
    """
    result = []
    for ch in text:
        cp = ord(ch)
        if cp in _MATH_SPECIAL:
            result.append(_MATH_SPECIAL[cp])
            continue
        mapped = False
        for start, end, base in _MATH_RANGES:
            if start <= cp <= end:
                result.append(chr(cp - start + base))
                mapped = True
                break
        if not mapped:
            result.append(ch)
    return ''.join(result)


def has_math_unicode(text: str) -> bool:
    return any(
        (start <= ord(ch) <= end)
        for ch in text
        for start, end, _ in _MATH_RANGES
    )

# ── Spatial fraction reconstruction ───────────────────────────────────────────

LINE_MERGE_TOL   = 3    # y-tolerance for word → line grouping
FRACTION_GAP_MAX = 16   # max vertical gap (pts) between numerator and denominator lines

# Full-width threshold: if a line spans >65% of page width it's prose, not a fraction part
FULLWIDTH_RATIO  = 0.65

# Width ratio cap: denominator must be ≤ this fraction of the numerator line's width
# This eliminates full-width prose pairs and continuation lines
DENOM_WIDTH_RATIO_MAX = 0.55


def _words_to_lines(words: list[dict], y_tol: int = LINE_MERGE_TOL) -> dict[float, list[dict]]:
    """Cluster words by vertical position into lines, sorted left-to-right within each."""
    buckets = defaultdict(list)
    for w in words:
        key = round(w['top'] / y_tol) * y_tol
        buckets[key].append(w)
    return {k: sorted(v, key=lambda w: w['x0']) for k, v in buckets.items()}


def _line_xrange(words: list[dict]) -> tuple[float, float]:
    return min(w['x0'] for w in words), max(w['x1'] for w in words)


def _line_width(words: list[dict]) -> float:
    x0, x1 = _line_xrange(words)
    return x1 - x0


def _x_overlap(r1: tuple, r2: tuple) -> float:
    return min(r1[1], r2[1]) - max(r1[0], r2[0])


def _is_fraction_pair(
    curr_words: list[dict],
    next_words: list[dict],
    page_width: float,
) -> bool:
    """
    Return True only if these two adjacent lines form a genuine stacked fraction.

    Rules (all must pass):
      1. At least one line contains Unicode math italic/bold characters
      2. Neither line is "full-width" prose (> FULLWIDTH_RATIO of page width)
      3. The denominator line (next) is narrower than the numerator:
         width(next) / width(curr) <= DENOM_WIDTH_RATIO_MAX
      4. There is horizontal x-overlap between the two lines (≥ 5 pts)
      5. Next line is not a new numbered step (i., ii., iii. etc.)
    """
    curr_text = normalize_math_unicode(' '.join(w['text'] for w in curr_words))
    next_text = normalize_math_unicode(' '.join(w['text'] for w in next_words))

    # Rule 1 — math content required
    if not (has_math_unicode(' '.join(w['text'] for w in curr_words)) or
            has_math_unicode(' '.join(w['text'] for w in next_words))):
        return False

    # Rule 2 — neither line is full-width prose
    w_curr = _line_width(curr_words)
    w_next = _line_width(next_words)
    if w_curr > page_width * FULLWIDTH_RATIO:
        return False
    if w_next > page_width * FULLWIDTH_RATIO:
        return False

    # Rule 3 — denominator is noticeably narrower than the line above
    if w_curr > 0 and (w_next / w_curr) > DENOM_WIDTH_RATIO_MAX:
        return False

    # Rule 4 — x-overlap
    r1 = _line_xrange(curr_words)
    r2 = _line_xrange(next_words)
    if _x_overlap(r1, r2) < 5:
        return False

    # Rule 5 — not a new numbered step
    if re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x)\.', next_text.strip(), re.IGNORECASE):
        return False

    return True


def _is_orphan_denominator(
    curr_words: list[dict],
    page_width: float,
) -> bool:
    """
    Detect lone denominator lines like standalone '12', '100', '25'
    that appear after a fraction line but weren't caught by the pair detector.
    These are short pure-numeric lines not preceded by a fraction pair.
    """
    text = ' '.join(w['text'] for w in curr_words).strip()
    width = _line_width(curr_words)
    # A very short purely numeric token that is much narrower than page
    return bool(re.match(r'^\d+$', text)) and width < page_width * 0.1


def reconstruct_fractions(words: list[dict], page_width: float) -> str:
    """
    Build readable text from page words by:
      - Grouping into lines
      - Detecting and merging genuine stacked fraction pairs
      - Discarding orphan-denominator lines
      - Normalizing math unicode throughout
    """
    lines    = _words_to_lines(words)
    tops     = sorted(lines.keys())
    used     = set()
    output   = []
    prev_was_fraction = False

    i = 0
    while i < len(tops):
        top = tops[i]
        if top in used:
            i += 1
            continue

        curr_words = lines[top]
        curr_text  = normalize_math_unicode(
            ' '.join(w['text'] for w in curr_words)
        ).strip()

        # Try to pair with next line as a fraction
        paired = False
        if i + 1 < len(tops):
            next_top   = tops[i + 1]
            gap        = next_top - top

            if gap <= FRACTION_GAP_MAX:
                next_words = lines[next_top]
                if _is_fraction_pair(curr_words, next_words, page_width):
                    next_text = normalize_math_unicode(
                        ' '.join(w['text'] for w in next_words)
                    ).strip()
                    output.append(f"({curr_text}) / ({next_text})")
                    used.add(top)
                    used.add(next_top)
                    prev_was_fraction = True
                    paired = True
                    i += 2
                    continue

        # Skip orphan denominators - DISABLED because it deletes question numbers (e.g. Q4, Q7)
        # if prev_was_fraction and _is_orphan_denominator(curr_words, page_width):
        #     used.add(top)
        #     prev_was_fraction = False
        #     i += 1
        #     continue

        output.append(curr_text)
        used.add(top)
        prev_was_fraction = False
        i += 1

    return '\n'.join(line for line in output if line.strip())

# ── Table → ASCII renderer ─────────────────────────────────────────────────────

def render_table(rows: list[list]) -> str:
    """Render pdfplumber table data as a clean ASCII grid."""
    if not rows:
        return ""
    clean = []
    for row in rows:
        clean_row = [
            normalize_math_unicode(str(c).replace('\n', ' ').strip()) if c else ''
            for c in row
        ]
        clean.append(clean_row)

    num_cols   = max(len(r) for r in clean)
    clean      = [r + [''] * (num_cols - len(r)) for r in clean]
    col_widths = [max(len(r[c]) for r in clean) for c in range(num_cols)]

    sep   = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'
    lines = [sep]
    for row in clean:
        cells = ' | '.join(cell.ljust(col_widths[ci]) for ci, cell in enumerate(row))
        lines.append('| ' + cells + ' |')
        lines.append(sep)
    return '\n'.join(lines)

# ── Page content extraction ────────────────────────────────────────────────────

# ── Vision extraction (for scanned PDFs) ──────────────────────────────────────

def extract_page_content_vision(image: Image.Image, prev_context: str = "") -> str:
    """
    Use OpenAI's vision model to extract text from a page image.
    Preserves question/answer structure and renders tables as ASCII.
    """
    # Pass previous context to avoid truncation at page boundaries
    context_note = ""
    if prev_context.strip():
        last_few = prev_context.strip()[-200:].replace('\n', ' ')
        context_note = f"\n\nCONTEXT FROM PREVIOUS PAGE: The previous page ended with: '...{last_few}'. If this page starts with a continuation of this sentence, ensure you capture it word-for-word before continuing with new content."

    # 1. Resize and compress to stay under 4MB
    max_dim = 2000 # Increased for better clarity
    if max(image.size) > max_dim:
        image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    base64_image = base64.b64encode(buf.getvalue()).decode("utf-8")

    prompt = (
        "You are a verbatim OCR system. Your goal is to extract ALL text visible in the provided image into a clean text stream.\n\n"
        "RULES:\n"
        "1. EXTRACT ALL: Extract every single word, including page numbers, headers, footers, and floating text. Do NOT summarize or omit any content.\n"
        "2. MAINTAIN LAYOUT: Keep paragraphs, question markers (e.g., 'Question 14'), and answers on their own lines as seen.\n"
        "3. TABLES: Extract tabular data into clean Markdown tables (| and -).\n"
        "4. DO NOT CLEAN: Do not attempt to strip 'noise', watermarks, or recurring headers. Extract them as seen. I will handle cleaning separate.\n"
        "5. CONTENT INTEGRITY: Do not add conversational text or formatting artifacts like triple backticks (```) for regular text."
    )

    try:
        response = openai_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            max_tokens=4000, # Increased for dense audit pages
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        log.error(f"  Vision extraction error: {e}")
        return ""

def _word_in_bbox(w: dict, bbox: tuple) -> bool:
    tx0, ty0, tx1, ty1 = bbox
    return (
        w['x0'] >= tx0 - 2 and w['x1'] <= tx1 + 2 and
        w['top'] >= ty0 - 2 and w['bottom'] <= ty1 + 2
    )


def extract_page_content(page) -> str:
    """
    Extract a single page with:
    - Tables as ASCII grids (spliced in at correct vertical position)
    - Prose with fraction reconstruction and math normalization
    - Correct ordering: tables slotted between prose blocks by y-position
    """
    page_width    = page.width
    table_objects = page.find_tables()
    tables_data   = page.extract_tables()
    table_bboxes  = [t.bbox for t in table_objects]

    # Words outside table regions only to avoid duplication with rendered tables
    all_words   = page.extract_words(
        keep_blank_chars=False, x_tolerance=3, y_tolerance=3
    )
    prose_words = [w for w in all_words
                   if not any(_word_in_bbox(w, bb) for bb in table_bboxes)]

    # Build prose text with fraction reconstruction
    prose_text = reconstruct_fractions(prose_words, page_width)

    # If no tables just return prose
    if not table_objects:
        return prose_text

    # ── Interleave prose lines and tables in vertical order ──────────────────
    # Assign each prose line an approximate y-position based on the first word
    # on that line. reconstruct_fractions processes tops in sorted order, so
    # we can safely map output line index → sorted_tops index.
    lines_dict  = _words_to_lines(prose_words)
    sorted_tops = sorted(lines_dict.keys())

    # We need to handle merged fraction lines (2 tops → 1 output line).
    # Re-run the same pairing logic just to get a (top, text) list.
    prose_tagged: list[tuple[float, str]] = []
    used: set = set()
    i = 0
    while i < len(sorted_tops):
        top = sorted_tops[i]
        if top in used:
            i += 1
            continue
        curr_words = lines_dict[top]
        curr_text  = normalize_math_unicode(
            ' '.join(w['text'] for w in curr_words)
        ).strip()

        paired = False
        if i + 1 < len(sorted_tops):
            next_top = sorted_tops[i + 1]
            gap      = next_top - top
            if gap <= FRACTION_GAP_MAX:
                next_words = lines_dict[next_top]
                if _is_fraction_pair(curr_words, next_words, page_width):
                    next_text = normalize_math_unicode(
                        ' '.join(w['text'] for w in next_words)
                    ).strip()
                    prose_tagged.append((top, f"({curr_text}) / ({next_text})"))
                    used.add(top); used.add(next_top)
                    i += 2; paired = True

        if not paired:
            prev_frac = (prose_tagged and '/' in prose_tagged[-1][1]
                         and prose_tagged[-1][1].startswith('('))
            if prev_frac and _is_orphan_denominator(curr_words, page_width):
                used.add(top); i += 1; continue
            if curr_text:
                prose_tagged.append((top, curr_text))
            used.add(top)
            i += 1

    # Build (y, text) list for tables
    table_tagged: list[tuple[float, str]] = [
        (tbl_obj.bbox[1], render_table(tbl_data))
        for tbl_obj, tbl_data in zip(table_objects, tables_data)
    ]

    # Merge and sort by y-position
    all_blocks = prose_tagged + table_tagged
    all_blocks.sort(key=lambda x: x[0])

    return '\n'.join(text for _, text in all_blocks if text.strip())


def is_page_scanned(page) -> bool:
    """Detect if a page is likely a scan (very little text compared to its area)."""
    text = page.extract_text() or ""
    # If a full page has fewer than 100 characters, it's almost certainly a scan or graphic
    return len(text.strip()) < 100

# ── Full PDF extraction ────────────────────────────────────────────────────────

# Matches page footer patterns like "3.1 | P a g e" or actual page numbers
_PAGE_FOOTER = re.compile(
    r'^\d+\.\d+\s*\|\s*(?:P\s*a\s*g\s*e|Page)$',   # e.g. 3.1 | Page
    re.IGNORECASE
)

# Common watermarks, banners, and noise to remove before chunking
# But we must be careful not to remove headers!
_NOISE_PATTERNS = [
    re.compile(r'F\s*O\s*C\s*A\s*S', re.IGNORECASE),
    re.compile(r'\bFO\b'), # Specific "FO" noise from "FOCAS"
    re.compile(r'\bCAS\b'),
    re.compile(r'Standards?\s+on\s+Auditing', re.IGNORECASE),
    re.compile(r'Risk\s+Assessment\s+and\s+Internal\s+Control', re.IGNORECASE),
    re.compile(r'Digital\s+Auditing\s+and\s+Assurance', re.IGNORECASE),
    re.compile(r'Group\s+Audits', re.IGNORECASE),
    re.compile(r'Special\s+Features\s+of\s+Audit\s+of\s+Banks\s+&\s+NBFCs', re.IGNORECASE),
    re.compile(r'Overview\s+of\s+Audit\s+of\s+Public\s+Sector\s+Undertakings', re.IGNORECASE),
    re.compile(r'BY\s+CA\s+ATUL\s+AGARWAL', re.IGNORECASE),
    re.compile(r'AIR1CA\s+Career\s+Institute', re.IGNORECASE),
    re.compile(r'A1R1?CA\s+Career\s+Institute', re.IGNORECASE), # Variant seen in OCR
    re.compile(r'\(AIR-?1\)', re.IGNORECASE),
    re.compile(r'\(ACI\)', re.IGNORECASE),
    re.compile(r'AUDIT\s+OF\s+CONSOLIDATED\s+FINANCIAL\s+STATEMENTS', re.IGNORECASE),
    re.compile(r'BY\s+CA\s+ATUL\s+AGARWAL\s+\(AIR-1\)', re.IGNORECASE),
    re.compile(r'\bA[I1\sRC]{1,6}A?\s*Career\s*Institute\s*\(ACI\)', re.IGNORECASE),
    re.compile(r'\bAIR1?CA\s*Career\s*Institute\s*\(ACI\)', re.IGNORECASE),
    re.compile(r'Page\s+\d+\.\d+', re.IGNORECASE),
    re.compile(r'LAST\s+ATTEMPT\s+KIT[:\s]*FM', re.IGNORECASE),
    re.compile(r'COST\s+OF\s+CAPITAL', re.IGNORECASE), # File specific banner
    re.compile(r'^SCOPE\s+&\s+OBJECTIVE.*', re.IGNORECASE),
    re.compile(r'^FM\s+SCOPE\s+&.*', re.IGNORECASE),
    re.compile(r"I'm\s+unable\s+to\s+assist\s+with\s+this\s+request", re.IGNORECASE),
    re.compile(r"I'm\s+unable\s+to\s+provide\s+a\s+verbatim\s+extraction", re.IGNORECASE),
    re.compile(r"These\s+tools\s+are\s+designed\s+to\s+recognize\s+and\s+digitize", re.IGNORECASE),
    re.compile(r"I\s*cannot\s*fulfill\s*this\s*request", re.IGNORECASE),
    re.compile(r"I\s+cannot\s+assist\s+with\s+this\s+request", re.IGNORECASE),
    re.compile(r"I\s+can't\s+assist\s+with\s+this\s+request", re.IGNORECASE),
    re.compile(r"as\s+an\s+AI\s+language\s+model", re.IGNORECASE),
    re.compile(r"Sure,\s+here\s+is\s+the\s+extracted\s+text", re.IGNORECASE),
    re.compile(r"Here\s+is\s+the\s+extracted\s+text", re.IGNORECASE),
    re.compile(r"Extracted\s+text\s+from\s+the\s+image", re.IGNORECASE),
]

def clean_text(text: str) -> str:
    lines   = text.splitlines()
    cleaned = []
    
    # Simple regex to check if a line is a header candidate
    header_check = re.compile(r'QUESTION|Q\.', re.IGNORECASE)
    
    for l in lines:
        s = l.strip()
        if not s:
            continue
            
        # 1. Skip page footers (e.g. 4.7 | Page or solitary 15)
        if _PAGE_FOOTER.match(s):
            continue
        
        # 2. Don't clean noise if it looks like a header (to protect it)
        if not header_check.search(s):
            for pat in _NOISE_PATTERNS:
                s = pat.sub('', s).strip()
            
        if not s:
            continue
        cleaned.append(s)
    
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(cleaned)).strip()
    # Final cleanup of stray backticks and markdown code block artifacts
    text = re.sub(r'```(?:markdown)?\n?', '', text)
    text = re.sub(r'```$', '', text)
    return text.strip()


def extract_pdf(pdf_path: str, force_vision: bool = False) -> str:
    """Extract all pages with fraction reconstruction. Falls back to Vision for scans."""
    parts = []
    
    # 1. First Pass: Check if the whole document is likely a scan
    is_scanned_doc = force_vision
    if not is_scanned_doc:
        with pdfplumber.open(pdf_path) as pdf:
            # Check first 3 pages
            checks = 0
            scanned_votes = 0
            for page in pdf.pages[:3]:
                checks += 1
                if is_page_scanned(page):
                    scanned_votes += 1
            if checks > 0 and scanned_votes / checks > 0.6:
                is_scanned_doc = True
                log.info(f"  🔍 Detected scanned PDF. Switching to Vision mode...")

    # 2. Extract based on type
    if is_scanned_doc:
        if not HAS_PDF2IMAGE:
            log.error("❌  'pdf2image' or 'poppler' missing. Cannot process scanned PDF.")
            return ""
        
        try:
            images = convert_from_path(pdf_path, dpi=300) # 300dpi for better table OCR
            log.info(f"  📸  Converted {len(images)} pages to images. Processing with {VISION_MODEL}...")
            last_extracted = ""
            for i, img in enumerate(images, 1):
                log.info(f"    🚀  Processing page {i}/{len(images)} with Vision...")
                try:
                    content = extract_page_content_vision(img, prev_context=last_extracted)
                    parts.append(content)
                    last_extracted = content
                except Exception as e:
                    log.error(f"  Vision Error on page {i}: {e}")
            return clean_text('\n'.join(parts))
        except Exception as e:
            log.error(f"  Critical error during PDF-to-Image conversion: {e}")
            return ""

    # 3. Standard text extraction fallback
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            try:
                # If a specific page is scanned in a digital document, we could still use vision
                if is_page_scanned(page):
                    if HAS_PDF2IMAGE:
                        log.info(f"  📸  Page {page_num} looks scanned. Using Vision fallback...")
                        # We have to convert just this page. Easier to convert all but more expensive.
                        # For now, we'll just use the standard fallback unless the whole doc is scanned.
                        # But let's try to get a single image if possible.
                        img = convert_from_path(pdf_path, first_page=page_num, last_page=page_num)[0]
                        content = extract_page_content_vision(img)
                        parts.append(content)
                        continue
                
                content = extract_page_content_vision(page) if force_vision else extract_page_content(page)
                parts.append(content)
            except Exception as e:
                log.warning(f"  Page {page_num} error: {e}")
                raw = page.extract_text() or ""
                parts.append(normalize_math_unicode(raw))
    return clean_text('\n'.join(parts))

# ── Question chunking ──────────────────────────────────────────────────────────

def parse_chapter(filename: str) -> str:
    m = re.search(r'chapter[_\s-]*(\d+)', filename, re.IGNORECASE)
    return m.group(1) if m else "unknown"


def split_q_and_a(body: str) -> tuple[str, str]:
    """Split question body at the first recognized Answer/Solution marker."""
    patterns = [
        # Standalone "Answer" line (even if it has spaces around it)
        r'(?:\n|^)\s*(?:ANSWER|Answer|SOLUTION|Solution)\b\s*[:\-\*\.]*\s*\n',
        # Markdown Bold or headers
        r'(?:\n|^)\s*(?:\*\*|#+)\s*(?:ANSWER|Answer|SOLUTION|Solution)\b\s*(?:\*\*)?[\s:\-\.]*',
        # Standard Colon style
        r'\b(?:ANSWER|Answer|SOLUTION|Solution|Soln?|Suggested\s+Answer|Suggested\s+Solution|Suggested\s+Soln)\s*[:\-\.]',
        # Permissive: any standalone "Answer" word
        r'\b(?:ANSWER|Answer|SOLUTION|Solution|Soln?)\b',
        # Table-style box
        r'\|\s*(?:ANSWER|Answer|SOLUTION|Solution|Soln?)\s*\|',
        # Fallback: Working Notes
        r'^\s*\|?\s*Working\s+Notes?\b',
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE | re.MULTILINE)
        if m:
            q_part = body[:m.start()].strip()
            a_part = body[m.start():].strip()
            
            # Clean up potential answer title leak into question
            q_lines = q_part.splitlines()
            if q_lines:
                last_line = q_lines[-1].strip()
                if last_line.endswith(':') and len(last_line) < 150:
                    q_part = '\n'.join(q_lines[:-1]).strip()
                    a_part = last_line + '\n' + a_part
            
            return q_part, a_part
    return body.strip(), ""


def chunk_by_question(text: str) -> list[dict]:
    """Split full PDF text into per-question chunks using a robust position-based approach."""
    # 1. Identify all "UNIT" headers to establish context boundaries
    unit_map = []
    unit_pattern = re.compile(r'^\s*UNIT\s*(\d+|[IVX]+)\b\s*[:\s-]+([^\n]+)', re.IGNORECASE | re.MULTILINE)
    for m in unit_pattern.finditer(text):
        u_val = m.group(1).upper()
        unit_map.append({
            "start": m.start(),
            "no":    u_val,
            "name":  m.group(2).strip()
        })
    unit_map.sort(key=lambda x: x["start"])

    # 2. Identify all "Question" headers with precise positions
    q_pattern = re.compile(r'(?:\n|^)\s*(?:\*\*|#+)?\s*(?:Question|Q\.?|Q\s*No\.?)\s*(\d+)\b(?:\*\*)?[:\s]*', re.IGNORECASE)
    
    matches = list(q_pattern.finditer(text))
    chunks_map = {}
    
    for i, m in enumerate(matches):
        q_num = str(int(m.group(1)))
        h_pos = m.start()
        
        next_pos = matches[i+1].start() if i+1 < len(matches) else len(text)
        raw_body = text[m.end():next_pos].strip()
        
        q_body, a_body = split_q_and_a(raw_body)
        
        # 3. Assign Unit based on current position
        current_unit = "1"
        current_unit_name = ""
        for u in unit_map:
            if u["start"] <= h_pos:
                current_unit = u["no"]
                current_unit_name = u["name"]
            else:
                break

        full_q_text = (f"Question {q_num}\n" + q_body).strip()
        full_content = (f"Question {q_num}\n" + raw_body).strip()
        group_key = f"{current_unit}_{q_num}"

        if group_key in chunks_map:
            existing = chunks_map[group_key]
            log.info(f"    🔗  Merging multiple fragments for Q{q_num} in Unit {current_unit}")
            if len(full_q_text) > len(existing["question_text"]):
                existing["question_text"] = full_q_text
            if len(a_body) > len(existing["answer_text"]):
                existing["answer_text"] = a_body
            existing["content"] += "\n\n" + full_content
        else:
            chunks_map[group_key] = {
                "question_no":   q_num,
                "unit":          current_unit,
                "unit_name":     current_unit_name,
                "question_text": full_q_text,
                "answer_text":   a_body,
                "content":       full_content,
                "chunk_idx":     len(chunks_map),
            }
    
    return sorted(chunks_map.values(), key=lambda x: x["chunk_idx"])

# ── Embedding + MongoDB upsert ─────────────────────────────────────────────────

openai_client = OpenAI(api_key=OPENAI_KEY, timeout=60.0)
mongo_client  = MongoClient(MONGODB_URI)
col           = mongo_client[DB_NAME][COLLECTION]


def embed_texts(texts: list[str]) -> list[list[float]]:
    safe = [t[:6000] for t in texts]
    resp = openai_client.embeddings.create(model=EMBED_MODEL, input=safe)
    return [item.embedding for item in resp.data]


def validate_chunk(chunk: dict) -> list[str]:
    warnings = []
    if not chunk.get('question_text'):
        warnings.append("Empty question_text")
    if not chunk.get('answer_text'):
        warnings.append("Empty answer_text — no ANSWER: marker found in extracted text")
    if has_math_unicode(chunk.get('content', '')):
        warnings.append("Residual math unicode in content (normalization incomplete)")
    return warnings


def ingest_pdf(pdf_path: str, level: str, subject: str, rel_path: str, verbose: bool = False, force_vision: bool = False):
    filename = os.path.basename(pdf_path)
    chapter  = parse_chapter(filename)
    log.info(f"📄  {filename}  (level={level}, subject={subject}, chapter={chapter})")

    full_text = extract_pdf(pdf_path, force_vision=force_vision)
    if not full_text.strip():
        log.warning(f"  ⚠️  No text could be extracted from {filename}. Skipping database update.")
        return

    if verbose:
        log.debug("=== Extracted text preview ===")
        for i, line in enumerate(full_text.splitlines()[:100], 1):
            log.debug(f"  {i:3d}: {line}")

    chunks = chunk_by_question(full_text)
    
    # Filter out chunks with empty content
    valid_chunks = [c for c in chunks if c.get('content', '').strip()]

    if not valid_chunks:
        log.warning(f"  ⚠️  No valid content found in {filename} after chunking. Skipping.")
        return

    log.info(f"  Found {len(valid_chunks)} valid question chunk(s)")

    for chunk in valid_chunks:
        for w in validate_chunk(chunk):
            log.warning(f"  Q{chunk['question_no']}: {w}")

    embeddings = embed_texts([c['content'] for c in valid_chunks])

    ops = []
    for chunk, emb in zip(valid_chunks, embeddings):
        # We include level, subject, unit and question in the ID to avoid collisions.
        safe_fn = re.sub(r'[^a-zA-Z0-9]', '_', filename).lower()
        doc_id = f"{level}_{subject}_ch{chapter}_u{chunk['unit']}_q{chunk['question_no']}_{safe_fn}"
        
        ops.append(UpdateOne(
            {"_id": doc_id},
            {"$set": {
                "_id":            doc_id,
                "level":          level,
                "subject":        subject,
                "chapter":        chapter,
                "unit":           chunk['unit'],
                "unit_name":      chunk['unit_name'],
                "question_no":    chunk['question_no'],
                "source_file":    filename,
                "question_text":  chunk['question_text'],
                "answer_text":    chunk['answer_text'],
                "content":        chunk['content'],
                "embedding":      emb,
                "ingested_at":    datetime.now(timezone.utc),
                "schema_version": 6, 
            }},
            upsert=True,
        ))

    result = col.bulk_write(ops)
    log.info(f"  ✅  Upserted {len(valid_chunks)} chunk(s)")
    save_ingested_file(rel_path, subject)


def ensure_indexes():
    col.create_index([("level", 1), ("subject", 1), ("chapter", 1), ("question_no", 1)])
    col.create_index([("source_file", 1)])
    log.info("  📌  Indexes ensured")

# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest study-material PDFs with formula-aware extraction"
    )
    parser.add_argument("--pdf_dir", default="./pdfs")
    parser.add_argument("--level", help="Manually set Level for all PDFs in this run")
    parser.add_argument("--subject", help="Manually set Subject for all PDFs in this run")
    parser.add_argument("--force_vision", action="store_true", help="Force OCR vision for all PDFs (use for scans)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    pdf_tasks = []
    # Walk the directory to find Level/Subject/PDF structure
    for root, dirs, files in os.walk(args.pdf_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                full_path = os.path.join(root, f)
                # Calculate relative path to extract metadata from folder names
                rel_path = os.path.relpath(full_path, args.pdf_dir)
                parts = rel_path.split(os.sep)

                # Detection logic from folders
                folder_level = "default"
                folder_subject = "default"
                
                if len(parts) >= 3:
                    folder_level   = parts[0]
                    folder_subject = parts[1]
                elif len(parts) == 2:
                    folder_subject = parts[0]

                # Priority: CLI argument > Folder structure
                final_level   = args.level   if args.level   else folder_level
                final_subject = args.subject if args.subject else folder_subject

                pdf_tasks.append((full_path, final_level, final_subject, rel_path))

    if not pdf_tasks:
        log.error(f"No PDFs found in {args.pdf_dir}")
        return

    ensure_indexes()
    
    # Cache for per-subject ingested lists to avoid multiple file reads
    ingested_by_subject = {}

    def is_ingested(path, sub):
        if sub not in ingested_by_subject:
            ingested_by_subject[sub] = get_ingested_files(sub)
        return path in ingested_by_subject[sub]

    to_process = []
    for pdf_path, level, subject, rel_path in sorted(pdf_tasks):
        if is_ingested(rel_path, subject):
            log.info(f"⏭️  Skipping {rel_path} (already ingested in {subject}.json)")
        else:
            to_process.append((pdf_path, level, subject, rel_path))

    if not to_process:
        log.info("\n✨ All files are already up to date. Nothing to ingest.")
        mongo_client.close()
        return

    log.info(f"🔍  Found {len(to_process)} new PDF(s) to ingest\n")

    for pdf_path, level, subject, rel_path in to_process:
        try:
            ingest_pdf(pdf_path, level, subject, rel_path, verbose=args.verbose, force_vision=args.force_vision)
        except Exception as e:
            log.error(f"❌  Failed: {pdf_path}: {e}", exc_info=True)

    mongo_client.close()
    log.info("\n🎉  Done!")


if __name__ == "__main__":
    main()