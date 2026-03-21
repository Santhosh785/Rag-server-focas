import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = "exam_db"
COLLECTION = "questions"

def cleanup_file(filename):
    client = MongoClient(MONGODB_URI)
    col = client[DB_NAME][COLLECTION]
    
    # 1. Delete all for this file
    res = col.delete_many({"source_file": filename})
    print(f"🗑️  Deleted {res.deleted_count} document(s) for {filename}")
    
    # 2. Also check for stray entries with same level/subject/chapter if any
    # (Optional, but good for safety)
    
    client.close()

if __name__ == "__main__":
    cleanup_file("Chapter_1_QUALITY CONTROL.pdf")
