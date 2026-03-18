import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME     = "exam_db"
COLLECTION  = "questions"
INGESTED_TRACKER = "ingested_files.json"

def sync():
    if not MONGODB_URI:
        print("❌ MONGODB_URI not set in .env")
        return

    client = MongoClient(MONGODB_URI)
    col = client[DB_NAME][COLLECTION]

    print("🔍 Fetching unique ingested files from MongoDB...")
    # Get unique source_file names from the collection
    unique_files = col.distinct("source_file")
    
    if not unique_files:
        print("ℹ️ No files found in the database.")
        unique_files = []

    print(f"✅ Found {len(unique_files)} unique files in DB.")

    # Load existing tracking file if it exists to merge
    existing = set()
    if os.path.exists(INGESTED_TRACKER):
        try:
            with open(INGESTED_TRACKER, "r") as f:
                existing = set(json.load(f))
        except:
            pass
    
    all_ingested = sorted(list(set(unique_files) | existing))

    with open(INGESTED_TRACKER, "w") as f:
        json.dump(all_ingested, f, indent=4)
    
    print(f"🚀 Updated {INGESTED_TRACKER} with {len(all_ingested)} files.")
    client.close()

if __name__ == "__main__":
    sync()
