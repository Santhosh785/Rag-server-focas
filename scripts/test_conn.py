import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv("MONGODB_URI")

try:
    print(f"Connecting to MongoDB...")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    print("Databases:", client.list_database_names())
    print("Connection successful!")
except Exception as e:
    print(f"Connection failed: {e}")
