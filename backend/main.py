import os
import io
import re
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches, RGBColor
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not found in environment")

DB_NAME = "exam_db"
COLLECTION = "questions"

# --- Setup ---
app = FastAPI()
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

# --- Helper for Styling ---
def set_cell_shading(cell, color):
    """Sets background color for a table cell."""
    shading_elm = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), color))
    cell._tc.get_or_add_tcPr().append(shading_elm)

def clean_val(val):
    if pd.isna(val): return ""
    if isinstance(val, (float, int)):
        if float(val).is_integer(): return str(int(val))
        return str(val)
    return str(val).strip()

@app.post("/api/generate-paper")
async def generate_paper(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Please upload an Excel file.")

    try:
        # 1. Read Excel
        contents = await file.read()
        df_raw = pd.read_excel(io.BytesIO(contents), header=None)
        
        # Header row detection
        header_row_index = 0
        required_keywords = {"question", "subject", "level", "chapter"}
        found_header = False
        for i, row in df_raw.iterrows():
            row_values = [str(val).lower() for val in row.values if pd.notna(val)]
            if sum(1 for kw in required_keywords if any(kw in val for val in row_values)) >= 3:
                header_row_index = i
                found_header = True
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

        # 2. Initialize Word Doc
        doc = Document()
        
        # Margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.4)
            section.bottom_margin = Inches(0.4)
            section.left_margin = Inches(0.6)
            section.right_margin = Inches(0.6)

        # Pull Metadata
        first_row = df.dropna(subset=['level', 'subject']).iloc[0] if not df.empty else None
        paper_level = clean_val(first_row.get('level', 'CA INTERMEDIATE')).upper()
        paper_subject = clean_val(first_row.get('subject', 'SUBJECT')).upper()

        # --- TOP HEADER BAR (Dark Blue) ---
        bar_table = doc.add_table(rows=1, cols=1)
        bar_table.width = Inches(7.3)
        cell = bar_table.rows[0].cells[0]
        set_cell_shading(cell, "002060") # Dark Blue
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("FOCAS EDU — LAST ATTEMPT KIT PRO")
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255) # White
        run.font.size = Pt(14)

        # --- EXAM TITLES ---
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        p_exam = doc.add_paragraph(f"{paper_level} EXAMINATION")
        p_exam.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_exam.add_run() # dummy run to ensure p.runs exists if needed
        p_exam.runs[0].bold = True
        p_exam.runs[0].font.size = Pt(13)
        
        p_sub = doc.add_paragraph(f"PAPER: {paper_subject}\nFULL TEST — MODEL PAPER")
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_sub.runs[0].bold = True
        p_sub.runs[0].font.size = Pt(11)

        # --- STATS ROW (Light Blue Table) ---
        stats_table = doc.add_table(rows=1, cols=3)
        stats_table.width = Inches(7.3)
        stats_table.style = 'Table Grid'
        
        # Robust Marks Sum
        total_marks = 100
        if 'marks' in df.columns:
            # Convert to numeric, replace garbage with 0
            m_numeric = pd.to_numeric(df['marks'], errors='coerce').fillna(0)
            total_marks = int(m_numeric.sum())
            if total_marks <= 0: total_marks = 100

        stats_data = [f"Total Marks: {total_marks}", "Time: 3 Hours", "Date: _________"]
        
        for i, text in enumerate(stats_data):
            c = stats_table.rows[0].cells[i]
            set_cell_shading(c, "CFE2F3") # Light Blue
            c.text = text
            cp = c.paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cp.runs[0].bold = True
            cp.runs[0].font.size = Pt(10)

        # --- GENERAL INSTRUCTIONS ---
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
        inst_bar = doc.add_table(rows=1, cols=1)
        inst_bar.width = Inches(7.3)
        inst_cell = inst_bar.rows[0].cells[0]
        set_cell_shading(inst_cell, "FFF2CC") # Pale Yellow
        ip = inst_cell.paragraphs[0]
        ip.add_run("GENERAL INSTRUCTIONS:").bold = True
        
        instructions = [
            "1. All questions are COMPULSORY.",
            "2. Marks are indicated against each question in brackets [ ].",
            "3. Answers should be based on relevant Study Material and standards."
        ]
        for inst in instructions:
            p_inst = doc.add_paragraph(inst)
            p_inst.style.font.size = Pt(9)
            p_inst.paragraph_format.left_indent = Inches(0.2)
            p_inst.paragraph_format.space_after = Pt(0)

        # --- PART BAR ---
        doc.add_paragraph().paragraph_format.space_after = Pt(6)
        part_table = doc.add_table(rows=1, cols=1)
        part_table.width = Inches(7.3)
        part_cell = part_table.rows[0].cells[0]
        set_cell_shading(part_cell, "002060") # Dark Blue
        pp = part_cell.paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_p = pp.add_run("PART — I")
        run_p.bold = True
        run_p.font.color.rgb = RGBColor(255, 255, 255)
        run_p.font.size = Pt(11)

        # 3. Retrieve and Format Questions
        questions_found = 0
        for index, row in df.iterrows():
            q_num = clean_val(row.get('question_number'))
            subject = clean_val(row.get('subject'))
            level = clean_val(row.get('level'))
            chapter = clean_val(row.get('chapter_number'))
            unit = clean_val(row.get('unit'))
            marks = clean_val(row.get('marks'))

            if not q_num: continue

            # Regex query for robustness
            query = {
                "level": {"$regex": f"^{re.escape(level)}$", "$options": "i"},
                "subject": {"$regex": f"^{re.escape(subject)}$", "$options": "i"},
                "chapter": {"$regex": f"^{re.escape(chapter)}$", "$options": "i"},
                "question_no": {"$regex": f"^{re.escape(q_num)}$", "$options": "i"}
            }
            if unit: # Only query by unit if it was provided in the Excel sheet
                query["unit"] = {"$regex": f"^{re.escape(unit)}$", "$options": "i"}
                
            question_data = col.find_one(query)
            
            if question_data:
                questions_found += 1
                q_text = question_data.get("question_text", "")
                
                # Clean prefix: "Question X" or "QUESTION NO X"
                q_text_clean = re.sub(r'^(?:QUESTION|Question)\s+(?:NO\s+)?\d+.*?\n', '', q_text, flags=re.IGNORECASE | re.DOTALL).strip()
                
                # Q-Header (Label Only)
                p_q = doc.add_paragraph()
                run_q_label = p_q.add_run(f"Q{q_num}. ")
                run_q_label.bold = True
                run_q_label.font.size = Pt(11)

                # Process content (Body + Tables)
                add_formatted_content(doc, q_text_clean)
                
                # Marks at the bottom right
                if marks:
                    p_marks = doc.add_paragraph()
                    p_marks.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    m_run = p_marks.add_run(f"[{marks} Marks]")
                    m_run.bold = True
                    m_run.font.color.rgb = RGBColor(192, 0, 0)
                    m_run.font.size = Pt(10)
                    p_marks.paragraph_format.space_after = Pt(6)
                
            else:
                logger.warning(f"❌ Not found in DB: Q{q_num} (L={level}, S={subject}, Ch={chapter})")

        if questions_found == 0:
            raise HTTPException(status_code=404, detail="No matching questions found in database.")

        # 4. Save and return
        output = io.BytesIO()
        doc.save(output)
        output.seek(0)
        filename = f"CA_Exam_Paper_{datetime.now().strftime('%Y%m%d')}.docx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Error generating paper: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def add_formatted_content(doc, text):
    """Detects ASCII tables in text and converts them to native Word tables."""
    lines = text.split('\n')
    table_lines = []
    
    for line in lines:
        stripped = line.strip()
        is_table_row = (stripped.startswith('+') and stripped.endswith('+')) or \
                      (stripped.startswith('|') and stripped.endswith('|'))
        
        if is_table_row:
            table_lines.append(line)
        else:
            if table_lines:
                create_word_table(doc, table_lines)
                table_lines = []
            if stripped or line == "":
                p = doc.add_paragraph(line)
                p.style.font.size = Pt(10)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0

    if table_lines:
        create_word_table(doc, table_lines)

def create_word_table(doc, table_lines):
    """Parses ASCII pipes into a proportional Word table."""
    data_rows = []
    for line in table_lines:
        if line.strip().startswith('|'):
            cells = [c.strip() for c in line.split('|') if c.strip() or '|' in line]
            if line.strip().startswith('|'): cells = cells[1:]
            if line.strip().endswith('|'): cells = cells[:-1]
            data_rows.append(cells)
    
    if not data_rows: return
    data_rows = [r for r in data_rows if any(r)]
    if not data_rows: return

    num_cols = max(len(row) for row in data_rows)
    table = doc.add_table(rows=len(data_rows), cols=num_cols)
    table.style = 'Table Grid'
    table.autofit = True
    
    for i, row in enumerate(data_rows):
        for j, val in enumerate(row):
            if j < num_cols:
                table.cell(i, j).text = val
                for p in table.cell(i, j).paragraphs:
                    p.style.font.size = Pt(9)
                    p.paragraph_format.space_after = Pt(0)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
