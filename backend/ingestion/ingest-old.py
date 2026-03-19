"""
ingest.py — Parse PDFs using pdfplumber's table-aware extraction.
Tables are extracted as structured data and stored as ASCII-bordered text.
Each document stores:
  question_text : problem statement (before ANSWER:)
  answer_text   : full worked solution (from ANSWER: onwards)
  content       : combined (used for embedding)

Usage:
    python ingest.py --pdf_dir ./pdfs
"""

import os
import re
import argparse
import json
import pdfplumber
from openai import OpenAI
from pymongo import MongoClient, UpdateOne
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

INGESTED_TRACKER = "ingested_files.json"

MONGODB_URI = os.environ.get("MONGODB_URI")
OPENAI_KEY  = os.environ.get("OPENAI_API_KEY")
if not MONGODB_URI:
    raise SystemExit("❌  MONGODB_URI not set.")
if not OPENAI_KEY:
    raise SystemExit("❌  OPENAI_API_KEY not set.")

DB_NAME     = "exam_db"
COLLECTION  = "questions"
EMBED_MODEL = "text-embedding-3-small"

openai_client = OpenAI(api_key=OPENAI_KEY)
mongo_client  = MongoClient(MONGODB_URI)
col           = mongo_client[DB_NAME][COLLECTION]

# ── Table → ASCII renderer ────────────────────────────────────────────────────

def render_table(rows: list[list]) -> str:
    """
    Convert a list-of-lists table (from pdfplumber) into a clean ASCII table.
    Handles None cells and multiline cell text.
    """
    if not rows:
        return ""

    # Normalize: replace None, flatten multiline cell text
    clean = []
    for row in rows:
        clean_row = []
        for cell in row:
            if cell is None:
                cell = ""
            cell = str(cell).replace("\n", " ").strip()
            clean_row.append(cell)
        clean.append(clean_row)

    num_cols   = max(len(r) for r in clean)
    clean      = [r + [""] * (num_cols - len(r)) for r in clean]
    col_widths = [max(len(r[c]) for r in clean) for c in range(num_cols)]

    sep  = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    lines = [sep]
    for row in clean:
        cells = " | ".join(cell.ljust(col_widths[ci]) for ci, cell in enumerate(row))
        lines.append("| " + cells + " |")
        lines.append(sep)
    return "\n".join(lines)

# ── Page text + table extraction ──────────────────────────────────────────────

def extract_page_content(page) -> str:
    """
    Extract a single page's content with tables replaced by ASCII-bordered versions.
    Strategy:
      1. Get bounding boxes of all tables on the page
      2. Extract plain text from non-table regions
      3. For each table, render it as ASCII and splice it in at the right position
    """
    tables      = page.extract_tables()
    table_bboxes = [t.bbox for t in page.find_tables()] if tables else []

    if not tables:
        return page.extract_text() or ""

    # Build a map: table_bbox → rendered ASCII table
    rendered_tables = {}
    for tbl_obj, tbl_data in zip(page.find_tables(), tables):
        rendered_tables[tbl_obj.bbox] = render_table(tbl_data)

    # Extract words with their positions; group by vertical position
    words = page.extract_words()
    if not words:
        return "\n".join(rendered_tables.values())

    def in_any_table(word):
        wx0, wy0, wx1, wy1 = word["x0"], word["top"], word["x1"], word["bottom"]
        for (tx0, ty0, tx1, ty1) in table_bboxes:
            if wx0 >= tx0 - 2 and wx1 <= tx1 + 2 and wy0 >= ty0 - 2 and wy1 <= ty1 + 2:
                return True
        return False

    # Group non-table words into lines (by rounded top position)
    from collections import defaultdict
    line_words = defaultdict(list)
    for w in words:
        if not in_any_table(w):
            key = round(w["top"])
            line_words[key].append(w)

    # Build ordered output: text lines + tables spliced at correct y position
    # Collect all y positions: text lines and table tops
    text_lines = {}
    for y, ws in line_words.items():
        ws_sorted = sorted(ws, key=lambda w: w["x0"])
        text_lines[y] = " ".join(w["text"] for w in ws_sorted)

    table_entries = {}
    for (tx0, ty0, tx1, ty1), rendered in rendered_tables.items():
        table_entries[int(ty0)] = rendered

    all_y = sorted(set(list(text_lines.keys()) + list(table_entries.keys())))

    output_parts = []
    seen_tables  = set()
    for y in all_y:
        if y in table_entries and y not in seen_tables:
            output_parts.append(table_entries[y])
            seen_tables.add(y)
        elif y in text_lines:
            output_parts.append(text_lines[y])

    return "\n".join(output_parts)

# ── Full PDF extraction ───────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    lines   = text.splitlines()
    cleaned = []
    for line in lines:
        s = line.strip()
        if re.match(r"^\d+\.\d+\s*\|\s*P\s*a\s*g\s*e$", s):
            continue
        if re.match(r"^[A-Z][A-Z\s:\'\&\-\.]{4,}$", s) and len(s) < 60:
            continue
        cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


def extract_pdf(pdf_path: str) -> str:
    """Extract full PDF text with tables as ASCII blocks."""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(extract_page_content(page))
    return clean_text("\n".join(parts))

# ── Chunking ──────────────────────────────────────────────────────────────────

def parse_chapter(filename: str) -> str:
    m = re.search(r"chapter[_\s-]*(\d+)", filename, re.IGNORECASE)
    return m.group(1) if m else "unknown"


def split_q_and_a(body: str) -> tuple[str, str]:
    """
    Split body into (question_text, answer_text).
    Priority order for split boundary:
      1. ANSWER:          — explicit marker (most common)
      2. ANSWER           — marker without colon
      3. Working Notes    — used when ANSWER: is absent (e.g. Q7 style)
    """
    patterns = [
        r"\bANSWER\s*:",          # ANSWER: (with colon)
        r"^ANSWER\s*$",            # ANSWER alone on a line
        r"^ANSWER\b",              # ANSWER at start of line
        r"^Working Notes?\s*$",    # Working Notes / Working Note
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE | re.MULTILINE)
        if m:
            return body[:m.start()].strip(), body[m.start():].strip()
    return body.strip(), ""


def chunk_by_question(text: str) -> list[dict]:
    pattern = re.compile(
        r'((?:QUESTION|Question)\s*(?:NO\.?|No\.?)?\s*\d+|Q\.?\s*NO\.?\s*\d+)',
        re.MULTILINE
    )
    splits  = pattern.split(text)

    chunks = []
    i = 1
    while i < len(splits) - 1:
        header    = splits[i].strip()
        body      = splits[i + 1].strip()
        num_match = re.search(r"\d+", header)
        q_num     = num_match.group() if num_match else str(i)
        q_text, a_text = split_q_and_a(body)

        chunks.append({
            "question_no":   q_num,
            "question_text": (header + "\n" + q_text).strip(),
            "answer_text":   a_text,
            "content":       (header + "\n" + body).strip(),
        })
        i += 2
    return chunks

# ── Embed + store ─────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    resp = openai_client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]


def get_ingested_files():
    if os.path.exists(INGESTED_TRACKER):
        try:
            with open(INGESTED_TRACKER, "r") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()


def save_ingested_file(filename):
    ingested = list(get_ingested_files())
    if filename not in ingested:
        ingested.append(filename)
        with open(INGESTED_TRACKER, "w") as f:
            json.dump(ingested, f, indent=4)


def ingest_pdf(pdf_path: str):
    filename = os.path.basename(pdf_path)
    chapter  = parse_chapter(filename)
    print(f"  📄 {filename}  (chapter={chapter})")

    full_text = extract_pdf(pdf_path)
    chunks    = chunk_by_question(full_text)

    if not chunks:
        print(f"  ⚠️  No question chunks found.")
        chunks = [{"question_no": "0", "question_text": full_text[:4000],
                   "answer_text": "", "content": full_text[:8000]}]

    embeddings = embed_texts([c["content"] for c in chunks])
    ops = []
    for chunk, emb in zip(chunks, embeddings):
        doc_id = f"ch{chapter}_q{chunk['question_no']}_{filename}"
        ops.append(UpdateOne(
            {"_id": doc_id},
            {"$set": {
                "_id":           doc_id,
                "chapter":       chapter,
                "question_no":   chunk["question_no"],
                "source_file":   filename,
                "question_text": chunk["question_text"],
                "answer_text":   chunk["answer_text"],
                "content":       chunk["content"],
                "embedding":     emb,
                "ingested_at":   datetime.now(timezone.utc),
            }},
            upsert=True,
        ))

    result = col.bulk_write(ops)
    print(f"  ✅ Upserted {result.upserted_count + result.modified_count} chunks")
    save_ingested_file(filename)


def ensure_indexes():
    col.create_index([("chapter", 1), ("question_no", 1)])
    col.create_index([("source_file", 1)])
    print("  📌 Indexes ensured.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf_dir", default="./pdfs")
    args = parser.parse_args()

    pdfs = [os.path.join(args.pdf_dir, f)
            for f in os.listdir(args.pdf_dir) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"No PDFs in {args.pdf_dir}"); return

    ensure_indexes()
    
    ingested_files = get_ingested_files()
    pdf_files = [f for f in os.listdir(args.pdf_dir) if f.lower().endswith(".pdf")]
    
    to_ingest = []
    for f in pdf_files:
        if f in ingested_files:
            print(f"  ⏭️  Skipping {f} (already ingested)")
        else:
            to_ingest.append(os.path.join(args.pdf_dir, f))

    if not to_ingest:
        print("\n✨ All files are already up to date. Nothing to ingest.")
        mongo_client.close()
        return

    print(f"\n🔍 Found {len(to_ingest)} new PDF(s) to ingest\n")
    for p in to_ingest:
        ingest_pdf(p)
    mongo_client.close()
    print("\n🎉 Done!")


if __name__ == "__main__":
    main()