import os
import io
import re
import pandas as pd
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv

# Local Imports
from backend.services.paper_service import build_paper_bundle_from_df
from backend.utils.text_utils import clean_val

load_dotenv()

# --- Config ---
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not found in environment")

DB_NAME = "exam_db"
COLLECTION = "questions"

# --- Setup ---
app = FastAPI(title="FOCAS Exam Paper Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DB Connection ---
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
col = db[COLLECTION]

# --- Models ---
class QuestionItem(BaseModel):
    level: str
    subject: str
    chapter_number: str
    unit: Optional[str] = ""
    question_number: str
    marks: Optional[str] = ""

class PaperRequest(BaseModel):
    questions: List[QuestionItem]

class RandomPaperRequest(BaseModel):
    level: str
    subject: str
    chapter_number: Optional[str] = ""
    total_marks: int = 50

# --- Helper Logic ---
def get_zip_filename(prefix="CA_Exam_Package"):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d')}.zip"

# --- Endpoints ---

@app.post("/api/generate-paper")
async def generate_paper(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Please upload an Excel file.")

    try:
        contents = await file.read()
        df_raw = pd.read_excel(io.BytesIO(contents), header=None)
        
        header_row_index = 0
        required_keywords = {"question", "subject", "level", "chapter"}
        for i, row in df_raw.iterrows():
            row_values = [str(val).lower() for val in row.values if pd.notna(val)]
            if sum(1 for kw in required_keywords if any(kw in val for val in row_values)) >= 3:
                header_row_index = i
                break
        
        df = pd.read_excel(io.BytesIO(contents), header=header_row_index)
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        column_mapping = {
            "question_number": ["question", "q_no", "q no", "number"],
            "subject": ["subject", "sub"],
            "level": ["level", "lvl"],
            "chapter_number": ["chapter", "ch_no", "ch no"],
            "unit": ["unit", "unit_no", "u_no", "u no"],
            "marks": ["marks", "mark", "pts", "points"]
        }
        for target, aliases in column_mapping.items():
            if target not in df.columns:
                for col_name in df.columns:
                    if any(alias in col_name for alias in aliases):
                        df.rename(columns={col_name: target}, inplace=True)
                        break
        
        zip_output = build_paper_bundle_from_df(df, col)
        if not zip_output:
            raise HTTPException(status_code=404, detail="No matching questions found in database.")

        return StreamingResponse(
            zip_output,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={get_zip_filename()}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating paper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-paper-json")
async def generate_paper_json(data: PaperRequest):
    try:
        df = pd.DataFrame([item.dict() for item in data.questions])
        if df.empty:
            raise HTTPException(status_code=400, detail="No questions provided in list.")
        
        zip_output = build_paper_bundle_from_df(df, col)
        if not zip_output:
            raise HTTPException(status_code=404, detail="No matching questions found in database.")

        return StreamingResponse(
            zip_output,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={get_zip_filename()}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating paper from JSON: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-random-paper")
async def generate_random_paper(data: RandomPaperRequest):
    try:
        query = {
            "level": {"$regex": f"^{re.escape(data.level)}$", "$options": "i"},
            "subject": {"$regex": f"^{re.escape(data.subject)}$", "$options": "i"}
        }
        if data.chapter_number:
            query["chapter"] = {"$regex": f"^{re.escape(data.chapter_number)}$", "$options": "i"}

        # Fetch a large sample
        pipeline = [{"$match": query}, {"$sample": {"size": 200}}]
        results = list(col.aggregate(pipeline))

        if not results:
            raise HTTPException(status_code=404, detail="No matching questions found in DB for this criteria.")

        selected_questions = []
        current_marks = 0

        for q in results:
            if current_marks >= data.total_marks:
                break
            
            q_text = q.get("question_text", "")
            # Extract marks looking for "[... X Marks ...]"
            marks_match = re.search(r'\[.*?(\d+)\s*Marks?', q_text, re.IGNORECASE)
            q_marks = int(marks_match.group(1)) if marks_match and marks_match.group(1).isdigit() else 5

            if current_marks + q_marks > data.total_marks + 2 and current_marks > 0:
                continue
                
            selected_questions.append({
                "level": q.get("level", data.level),
                "subject": q.get("subject", data.subject),
                "chapter_number": q.get("chapter", data.chapter_number or ""),
                "unit": q.get("unit", ""),
                "question_number": q.get("question_no", ""),
                "marks": str(q_marks)
            })
            current_marks += q_marks

        if not selected_questions:
             raise HTTPException(status_code=400, detail="Could not create paper with requested marks.")

        df = pd.DataFrame(selected_questions)
        zip_output = build_paper_bundle_from_df(df, col)
        if not zip_output:
            raise HTTPException(status_code=404, detail="Could not generate paper package.")

        return StreamingResponse(
            zip_output,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={get_zip_filename('FOCAS_Random_Package')}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating random paper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
