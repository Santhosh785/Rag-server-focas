import os
import re
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = "exam_db"
COLLECTION = "questions"

def clean_text(text):
    if not text:
        return text
    
    # 1. Remove "Standards on Auditing" footers/headers often inside code blocks
    # Handle cases like ```\nStandards on Auditing\n``` or just Standards on Auditing
    text = re.sub(r'```\s*Standards on Auditing\s*```', '', text)
    text = re.sub(r'```\s*Standards on Auditing', '', text)
    text = re.sub(r'Standards on Auditing\s*```', '', text)
    text = re.sub(r'^\s*Standards on Auditing\s*$', '', text, flags=re.MULTILINE)
    
    # 2. Remove Atul Agarwal specific noise
    text = re.sub(r'BY\s+CA\s+ATUL\s+AGARWAL\s+\(AIR-1\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'AIR1CA\s+Career\s+Institute\s+\(ACI\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Page\s+\d+\.\d+', '', text, flags=re.IGNORECASE)

    # 3. Remove LLM artifacts
    text = re.sub(r"Sure, here's the extracted text:.*?\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```markdown\n", "", text)
    text = re.sub(r"```plaintext\n", "", text)
    
    # 4. Clean up orphaned backticks and extra newlines
    text = re.sub(r'^\s*```\s*$', '', text, flags=re.MULTILINE)
    
    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def main():
    print(f"Connecting to MongoDB: {DB_NAME}...")
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Force a connection test
        client.admin.command('ping')
        print("✅ Connection successful!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    col = client[DB_NAME][COLLECTION]
    
    # --- Part 2: Global Cleanup of Footers ---
    print("Sweep: cleaning up headers/footers in all documents...")
    all_docs = col.find({}, {"question_text": 1, "answer_text": 1, "content": 1})
    count = 0
    processed_count = 0
    
    # We use a batch size to avoid long initial wait
    for doc in all_docs:
        updated = False
        fields_to_update = {}
        
        for field in ["question_text", "answer_text", "content"]:
            val = doc.get(field)
            if val:
                cleaned = clean_text(val)
                if cleaned != val:
                    fields_to_update[field] = cleaned
                    updated = True
        
        if updated:
            col.update_one({"_id": doc["_id"]}, {"$set": fields_to_update})
            count += 1
            
        processed_count += 1
        if processed_count % 50 == 0:
            print(f"   ... processed {processed_count} documents")
    
    print(f"✅ Cleaned up {count} documents total out of {processed_count} checked.")
    client.close()

if __name__ == "__main__":
    main()
