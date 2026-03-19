"""
query.py — Query PDF Q&A system. Tables are pre-rendered as ASCII during ingestion.

Usage:
    python query.py --chapter 3 --question 1
    python query.py --chapter 3 --question 7
    python query.py --text "gross profit ratio formula"
    python query.py          ← interactive mode
"""

import os
import re
import argparse
from openai import OpenAI
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI")
OPENAI_KEY  = os.environ.get("OPENAI_API_KEY")
if not MONGODB_URI:
    raise SystemExit("❌  MONGODB_URI not set.")
if not OPENAI_KEY:
    raise SystemExit("❌  OPENAI_API_KEY not set.")

DB_NAME            = "exam_db"
COLLECTION         = "questions"
EMBED_MODEL        = "text-embedding-3-small"
CHAT_MODEL         = "gpt-4o"
ATLAS_VECTOR_INDEX = "vector_index"

openai_client = OpenAI(api_key=OPENAI_KEY)
mongo_client  = MongoClient(MONGODB_URI)
col           = mongo_client[DB_NAME][COLLECTION]

DIVIDER = "=" * 72

# ── Retrieval ─────────────────────────────────────────────────────────────────

def embed_query(text: str) -> list[float]:
    return openai_client.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding


def fetch_exact(chapter: str, question_no: str) -> dict | None:
    return col.find_one(
        {"chapter": chapter, "question_no": question_no},
        {"_id": 0, "question_text": 1, "answer_text": 1,
         "content": 1, "chapter": 1, "question_no": 1, "source_file": 1}
    )


def fetch_semantic(query_text: str, chapter: str = None, top_k: int = 3) -> list[dict]:
    pre_filter = {"chapter": {"$eq": chapter}} if chapter else {}
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
                "_id": 0, "question_text": 1, "answer_text": 1,
                "content": 1, "chapter": 1, "question_no": 1, "source_file": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        }
    ]
    return list(col.aggregate(pipeline))

# ── Display ────────────────────────────────────────────────────────────────────

def display(doc: dict):
    """
    Print question and answer from their separate stored fields.
    Tables are already ASCII-formatted in the stored text (done at ingest time).
    """
    ch     = doc.get("chapter", "?")
    q_no   = doc.get("question_no", "?")
    src    = doc.get("source_file", "")

    q_text = doc.get("question_text", "").strip()
    a_text = doc.get("answer_text", "").strip()

    # Fallback: if old doc without split fields, use content
    if not q_text and not a_text:
        q_text = doc.get("content", "").strip()
        a_text = ""

    print(f"\n{DIVIDER}")
    print(f"  Chapter {ch}  |  Question {q_no}  |  {src}")
    print(DIVIDER)

    if q_text:
        print("\n── QUESTION " + "─" * 59)
        print(q_text)

    if a_text:
        print("\n── ANSWER " + "─" * 61)
        print(a_text)

    print(f"\n{DIVIDER}\n")

# ── LLM fallback for free-text ────────────────────────────────────────────────

def llm_answer(chunks: list[dict], user_question: str) -> str:
    ctx = "\n\n---\n\n".join(
        f"[Ch{c['chapter']} Q{c['question_no']}]\n"
        f"QUESTION:\n{c.get('question_text','')}\n\n"
        f"ANSWER:\n{c.get('answer_text', c.get('content',''))}"
        for c in chunks
    )
    prompt = (
        "You are an exam tutor. Answer using ONLY the context below. "
        "Plain text only, no LaTeX, no markdown bold.\n\n"
        f"CONTEXT:\n{ctx}\n\nUSER QUESTION:\n{user_question}\n\nANSWER:"
    )
    resp = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

# ── Main ask ──────────────────────────────────────────────────────────────────

def ask(chapter: str = None, question_no: str = None, free_text: str = None):
    # 1. Exact match → display directly
    if chapter and question_no:
        doc = fetch_exact(chapter, question_no)
        if doc:
            display(doc)
            return
        print(f"⚠️  No exact match for Ch{chapter} Q{question_no}. Trying vector search...")

    # 2. Semantic search
    search_text = free_text or f"Chapter {chapter} Question {question_no}"
    chunks = fetch_semantic(search_text, chapter=chapter, top_k=3)

    if not chunks:
        print("❌ No content found. Run ingest.py first.")
        return

    # Single semantic hit → display directly
    if len(chunks) == 1:
        display(chunks[0])
        return

    # Multiple hits → use LLM to synthesize
    answer = llm_answer(chunks, free_text or search_text)
    print(f"\n{DIVIDER}")
    print(f"  Semantic result: \"{free_text or search_text}\"")
    print(DIVIDER)
    print(answer)
    print(f"\n{DIVIDER}\n")

# ── CLI ───────────────────────────────────────────────────────────────────────

def interactive_loop():
    print("\n📚 PDF Q&A  |  type 'exit' to quit")
    print("Examples:  chapter 3 question 1  |  ch3 q7  |  gross profit ratio\n")
    while True:
        raw = input("You: ").strip()
        if raw.lower() in ("exit", "quit", "q"):
            break
        if not raw:
            continue
        ch_m = re.search(r"ch(?:apter)?\s*(\d+)", raw, re.IGNORECASE)
        q_m  = re.search(r"q(?:uestion)?\s*(?:no\.?)?\s*(\d+)", raw, re.IGNORECASE)
        ask(chapter=ch_m.group(1) if ch_m else None,
            question_no=q_m.group(1) if q_m else None,
            free_text=raw)
    mongo_client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter",  "-c")
    parser.add_argument("--question", "-q")
    parser.add_argument("--text",     "-t")
    args = parser.parse_args()

    if not any([args.chapter, args.question, args.text]):
        interactive_loop()
        return

    ask(chapter=args.chapter, question_no=args.question, free_text=args.text)
    mongo_client.close()


if __name__ == "__main__":
    main()