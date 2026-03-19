"""
query.py — Query PDF Q&A system.
Formulas are stored as reconstructed plain text (no LaTeX, no broken fractions).

Usage:
    python query.py --chapter 3 --question 1
    python query.py --chapter 3 --question 7
    python query.py --text "gross profit ratio formula"
    python query.py          ← interactive mode
"""

import os
import re
import argparse
import logging

from openai import OpenAI
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI        = os.environ.get("MONGODB_URI")
OPENAI_KEY         = os.environ.get("OPENAI_API_KEY")
if not MONGODB_URI:
    raise SystemExit("❌  MONGODB_URI not set.")
if not OPENAI_KEY:
    raise SystemExit("❌  OPENAI_API_KEY not set.")

DB_NAME            = "exam_db"
COLLECTION         = "questions"
EMBED_MODEL        = "text-embedding-3-small"
CHAT_MODEL         = "gpt-4o"
ATLAS_VECTOR_INDEX = "vector_index"

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

openai_client = OpenAI(api_key=OPENAI_KEY)
mongo_client  = MongoClient(MONGODB_URI)
col           = mongo_client[DB_NAME][COLLECTION]

DIVIDER = "=" * 72

# ── Retrieval ──────────────────────────────────────────────────────────────────

def embed_query(text: str) -> list[float]:
    return openai_client.embeddings.create(
        model=EMBED_MODEL, input=[text]
    ).data[0].embedding


def fetch_exact(chapter: str, question_no: str, level: str = None, subject: str = None) -> dict | None:
    query = {"chapter": chapter, "question_no": question_no}
    if level:   query["level"]   = level
    if subject: query["subject"] = subject
    
    return col.find_one(
        query,
        {"_id": 0, "question_text": 1, "answer_text": 1, "level": 1, "subject": 1,
         "content": 1, "chapter": 1, "question_no": 1, "source_file": 1}
    )


def fetch_semantic(query_text: str, level: str = None, subject: str = None, chapter: str = None, top_k: int = 3) -> list[dict]:
    pre_filter = {}
    if level:   pre_filter["level"]   = {"$eq": level}
    if subject: pre_filter["subject"] = {"$eq": subject}
    if chapter: pre_filter["chapter"] = {"$eq": chapter}
    pipeline = [
        {
            "$vectorSearch": {
                "index":         ATLAS_VECTOR_INDEX,
                "path":          "embedding",
                "queryVector":   embed_query(query_text),
                "numCandidates": top_k * 10,
                "limit":         top_k,
                **({"filter": pre_filter} if pre_filter else {}),
            }
        },
        {
            "$project": {
                "_id": 0, "question_text": 1, "answer_text": 1, "level": 1, "subject": 1,
                "content": 1, "chapter": 1, "question_no": 1, "source_file": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        }
    ]
    return list(col.aggregate(pipeline))

# ── Display ────────────────────────────────────────────────────────────────────

def display(doc: dict):
    """
    Print question and answer. Fractions appear as (NUMER) / (DENOM) in plain text,
    which is readable in terminal and safe for LLM consumption.
    """
    lvl    = doc.get("level", "default")
    sub    = doc.get("subject", "default")
    ch     = doc.get("chapter", "?")
    q_no   = doc.get("question_no", "?")
    src    = doc.get("source_file", "")

    q_text = doc.get("question_text", "").strip()
    a_text = doc.get("answer_text", "").strip()

    # Fallback for old documents without split fields
    if not q_text and not a_text:
        q_text = doc.get("content", "").strip()
        a_text = ""

    print(f"\n{DIVIDER}")
    print(f"  {lvl} > {sub} | Ch {ch}  |  Q {q_no}  |  {src}")
    print(DIVIDER)

    if q_text:
        print("\n── QUESTION " + "─" * 59)
        print(q_text)

    if a_text:
        print("\n── ANSWER " + "─" * 61)
        print(a_text)

    print(f"\n{DIVIDER}\n")

# ── LLM synthesis for free-text queries ───────────────────────────────────────

def llm_answer(chunks: list[dict], user_question: str) -> str:
    """
    Use GPT-4o to synthesize an answer from retrieved chunks.
    Fractions in context are already plain text — no LaTeX needed.
    """
    ctx = "\n\n---\n\n".join(
        f"[{c.get('level', 'default')} {c.get('subject', 'default')} Ch{c['chapter']} Q{c['question_no']}]\n"
        f"QUESTION:\n{c.get('question_text', '')}\n\n"
        f"ANSWER:\n{c.get('answer_text', c.get('content', ''))}"
        for c in chunks
    )
    prompt = (
        "You are an exam tutor specialising in financial management and ratio analysis.\n"
        "Answer using ONLY the context below.\n"
        "Fractions in the context are written as (NUMERATOR) / (DENOMINATOR) — preserve this format.\n"
        "Use plain text only. No LaTeX. No markdown bold.\n\n"
        f"CONTEXT:\n{ctx}\n\n"
        f"STUDENT QUESTION:\n{user_question}\n\n"
        "ANSWER:"
    )
    resp = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

# ── Main ask ───────────────────────────────────────────────────────────────────

def ask(level: str = None, subject: str = None, chapter: str = None, question_no: str = None, free_text: str = None):
    # 1. Exact match by chapter + question number
    if chapter and question_no:
        doc = fetch_exact(chapter, question_no, level=level, subject=subject)
        if doc:
            display(doc)
            return
        print(f"⚠️  No exact match (level={level}, sub={subject}, ch={chapter}, q={question_no}). Trying semantic...")

    # 2. Semantic search
    search_text = free_text or f"{level} {subject} Chapter {chapter} Question {question_no}"
    chunks      = fetch_semantic(search_text, level=level, subject=subject, chapter=chapter, top_k=3)

    if not chunks:
        print("❌  No content found. Run ingest.py first.")
        return

    if len(chunks) == 1:
        display(chunks[0])
        return

    # Multiple hits → LLM synthesis
    answer = llm_answer(chunks, free_text or search_text)
    print(f"\n{DIVIDER}")
    print(f"  Semantic result: \"{free_text or search_text}\"")
    print(DIVIDER)
    print(answer)
    print(f"\n{DIVIDER}\n")

# ── Interactive mode ───────────────────────────────────────────────────────────

def interactive_loop():
    print("\n📚  PDF Q&A  |  type 'exit' to quit")
    print("Examples:  chapter 3 question 1  |  ch3 q7  |  gross profit ratio\n")
    while True:
        try:
            raw = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if raw.lower() in ("exit", "quit", "q"):
            break
        if not raw:
            continue
        ch_m = re.search(r"ch(?:apter)?\s*(\d+)", raw, re.IGNORECASE)
        q_m  = re.search(r"q(?:uestion)?\s*(?:no\.?)?\s*(\d+)", raw, re.IGNORECASE)
        ask(
            chapter     = ch_m.group(1) if ch_m else None,
            question_no = q_m.group(1)  if q_m  else None,
            free_text   = raw,
        )
    mongo_client.close()

# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Query study-material Q&A stored in MongoDB"
    )
    parser.add_argument("--level",    "-l", help="Level (e.g. Final)")
    parser.add_argument("--subject",  "-s", help="Subject (e.g. FM, SM)")
    parser.add_argument("--chapter",  "-c", help="Chapter number")
    parser.add_argument("--question", "-q", help="Question number")
    parser.add_argument("--text",     "-t", help="Free-text search query")
    args = parser.parse_args()

    if not any([args.level, args.subject, args.chapter, args.question, args.text]):
        interactive_loop()
        return

    ask(level=args.level, subject=args.subject, chapter=args.chapter, 
        question_no=args.question, free_text=args.text)
    mongo_client.close()


if __name__ == "__main__":
    main()