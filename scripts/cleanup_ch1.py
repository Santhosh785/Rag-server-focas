from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = "exam_db"
COLLECTION = "questions"

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
col = db[COLLECTION]

target_file = "Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"

# Find q0
q0 = col.find_one({"source_file": target_file, "question_no": "0"})

if q0:
    print(f"Found Question 0 for {target_file}. Deleting...")
    result = col.delete_one({"_id": q0["_id"]})
    print(f"Deleted {result.deleted_count} document(s).")
else:
    print(f"No Question 0 found for {target_file}. Database is clean.")

client.close()
