"""
verify_ingestion.py — Automatically compare PDF source text against MongoDB chunks to find missing questions.
"""

import os
import re
import argparse
import pdfplumber
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME     = "exam_db"
COLLECTION  = "questions"

def extract_pdf_questions(pdf_path):
    """
    Extract expected question numbers from the PDF using the same regex as ingest.py
    """
    pattern = re.compile(
        r'\b(?:QUESTION|Question|Q\.?)\s*(?:NO\.?|No\.?)?\s*(\d+)',
        re.IGNORECASE
    )
    
    found_nums = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                matches = pattern.findall(text)
                for m in matches:
                    found_nums.add(str(int(m))) # Convert to int then back to string to normalize "01" -> "1"
    
    return sorted(list(found_nums), key=int)

def main():
    parser = argparse.ArgumentParser(description="Verify if all questions from PDF are in MongoDB")
    parser.add_argument("--pdf", required=True, help="Path to the PDF file to check")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"❌ File not found: {args.pdf}")
        return

    # 1. Extract expected question numbers from PDF
    print(f"🔍 Scanning PDF: {os.path.basename(args.pdf)}...")
    expected_nums = extract_pdf_questions(args.pdf)
    print(f"📋 Found {len(expected_nums)} potential questions in PDF: {', '.join(expected_nums)}")

    # 2. Fetch ingested questions from MongoDB
    client = MongoClient(MONGODB_URI)
    col = client[DB_NAME][COLLECTION]
    
    filename = os.path.basename(args.pdf)
    db_results = list(col.find({"source_file": filename}, {"question_no": 1}))
    ingested_nums = set(doc["question_no"] for doc in db_results)
    
    client.close()

    # 3. Compare and Diagnose
    missing = [n for n in expected_nums if n not in ingested_nums]
    
    print("\n" + "="*50)
    print(f"📊 REPORT FOR: {filename}")
    print("="*50)
    print(f"✅ Total Ingested: {len(ingested_nums)}")
    
    client = MongoClient(MONGODB_URI)
    col = client[DB_NAME][COLLECTION]

    if not missing:
        print("🎉 SUCCESS: All questions found in PDF are present in the database!")
    else:
        print(f"❌ MISSING: {len(missing)} questions found in PDF but NOT in database.")
        print(f"👉 Missing IDs: {', '.join(missing)}")
        
        print("\n🔍 DIAGNOSIS:")
        for m_id in missing:
            # Look at the question before the missing one to see if it was merged
            try:
                prev_id = str(int(m_id) - 1)
                prev_doc = col.find_one({"source_file": filename, "question_no": prev_id})
                if prev_doc:
                    content = prev_doc.get("content", "")
                    # Search for the missing header in the previous question's text
                    header_pattern = rf'(QUESTION|Question|Q\.?)\s*(NO\.?|No\.?)?\s*0*{m_id}\b'
                    if re.search(header_pattern, content, re.IGNORECASE):
                        print(f"  ⚠️  Question {m_id} was MERGED into Question {prev_id}.")
                        print(f"     Reason: No clear 'Answer:' marker was found after Question {m_id} header.")
                        continue
            except:
                pass
            
            print(f"  ❓  Question {m_id} was SKIPPED entirely or header was not recognized.")

        print("\n💡 Suggested Fixes:")
        print("1. Check the PDF text: Is there a clear 'Answer:' or 'Solution:' label?")
        print("2. If not, add a blank line or manual label in the PDF (if possible) and re-ingest.")
        print("3. Or manually split the content in the database.")
    
    client.close()

if __name__ == "__main__":
    main()
