import os
import re
import json
import argparse
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise SystemExit("❌  MONGODB_URI not set in .env")

DB_NAME     = "exam_db"
COLLECTION  = "questions"

def get_sort_key(doc):
    """
    Generate a sort key that handles:
    - Chapter as an integer
    - Question number as an integer if possible, or a comparable string
    """
    
    def to_int(s):
        if not s: return 0
        try:
            # Handle cases like "1", "12"
            return int(s)
        except ValueError:
            # Handle cases like "1A", "Q1" by extracting the digits
            m = re.search(r'\d+', str(s))
            if m:
                return int(m.group())
            # Handle Roman Numerals or other strings by returning a large number or 0
            # For now, 0 or simple string length for sorting
            return 0

    return (
        doc.get("level", ""),
        doc.get("subject", ""),
        to_int(doc.get("chapter", "0")),
        to_int(doc.get("unit", "0")),
        to_int(doc.get("question_no", "0")),
        str(doc.get("question_no", "")) # Secondary sort for alphanumeric like 1A, 1B
    )

def main():
    import re # Needed for the sort key regex
    parser = argparse.ArgumentParser(description="Export questions to Markdown")
    parser.add_argument("--chapter", "-c", help="Filter by Chapter number")
    parser.add_argument("--unit",    "-u", help="Filter by Unit number")
    parser.add_argument("--level",   "-l", help="Filter by Level (e.g. Final, Intermediate)")
    parser.add_argument("--subject", "-s", help="Filter by Subject (e.g. FM, SM)")
    args = parser.parse_args()

    mongo_client = MongoClient(MONGODB_URI)
    col          = mongo_client[DB_NAME][COLLECTION]

    # Build the filter query
    query = {}
    if args.chapter: query["chapter"] = args.chapter
    if args.unit:    query["unit"]    = args.unit
    if args.level:   query["level"]   = args.level
    if args.subject: query["subject"] = args.subject

    print(f"🔍  Fetching questions with filter: {query if query else 'All'}...")
    
    # We fetch everything then sort in Python for natural number sorting
    docs = list(col.find(query))

    if not docs:
        print("❌  No questions found matching your filters.")
        return

    # Sort manually to handle "natural" number sorting (1, 2, 10 instead of 1, 10, 2)
    docs.sort(key=get_sort_key)

    # Create descriptive filename
    filename_parts = ["export"]
    if args.level:   filename_parts.append(args.level)
    if args.subject: filename_parts.append(args.subject)
    if args.chapter: filename_parts.append(f"ch{args.chapter}")
    output_file = "_".join(filename_parts) + ".md"

    print(f"📄  Found {len(docs)} questions. Sorting properly and writing to {output_file}...")

    with open(output_file, "w", encoding="utf-8") as f:
        title = f"Questions: {' '.join(filename_parts[1:])}" if len(filename_parts) > 1 else "All Questions"
        f.write(f"# {title}\n\n")
        f.write(f"Total questions: **{len(docs)}**\n\n---\n\n")

        for doc in docs:
            lvl  = doc.get("level", "default")
            sub  = doc.get("subject", "default")
            ch   = doc.get("chapter", "?")
            unt  = doc.get("unit", "")
            unt_name = doc.get("unit_name", "")
            q_no = doc.get("question_no", "?")
            src  = doc.get("source_file", "unknown")
            
            q_text = doc.get("question_text", "").strip()
            a_text = doc.get("answer_text", "").strip()

            unit_str = f" | Unit {unt}" if unt else ""
            if unt_name:
                unit_str += f": {unt_name}"

            f.write(f"## {lvl} > {sub} | Chapter {ch}{unit_str} | Question {q_no}\n")
            f.write(f"*Source: {src}*\n\n")

            if q_text:
                f.write("### QUESTION\n")
                f.write(q_text + "\n\n")

            if a_text:
                f.write("### ANSWER\n")
                f.write(a_text + "\n\n")

            f.write("---\n\n")

    print(f"✅  Done! Check '{output_file}'.")
    mongo_client.close()

if __name__ == "__main__":
    main()
