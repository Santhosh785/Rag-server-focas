import io
import re
import zipfile
import pandas as pd
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import logging

from backend.utils.docx_utils import (
    set_cell_shading,
    add_formatted_content
)
from backend.utils.text_utils import (
    clean_val,
    clean_question_text
)

logger = logging.getLogger(__name__)

def build_paper_bundle_from_df(df: pd.DataFrame, col) -> io.BytesIO:
    # 1. Initialize Word Docs
    qp_doc = Document()
    ak_doc = Document()
    
    # Common margins
    for doc in [qp_doc, ak_doc]:
        for section in doc.sections:
            section.top_margin = Inches(0.5)
            section.bottom_margin = Inches(0.5)
            section.left_margin = Inches(0.65)
            section.right_margin = Inches(0.65)

    # Pull Metadata
    first_row = df.dropna(subset=['level', 'subject']).iloc[0] if not df.empty else None
    paper_level = clean_val(first_row.get('level', 'CA INTERMEDIATE')) if first_row is not None else 'CA INTERMEDIATE'
    paper_level = paper_level.upper()
    paper_subject = clean_val(first_row.get('subject', 'SUBJECT')) if first_row is not None else 'SUBJECT'
    paper_subject = paper_subject.upper()

    # Total Marks
    total_marks = 100
    if 'marks' in df.columns:
        m_numeric = pd.to_numeric(df['marks'], errors='coerce').fillna(0)
        total_marks = int(m_numeric.sum())
        if total_marks <= 0: total_marks = 100

    # --- Setup Headers for Both ---
    for doc, title_tag in [(qp_doc, "MODEL PAPER"), (ak_doc, "ANSWER KEY")]:
        # TOP HEADER BAR
        bar_table = doc.add_table(rows=1, cols=1)
        bar_table.width = Inches(7.2)
        bar_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = bar_table.rows[0].cells[0]
        set_cell_shading(cell, "002060") # Dark Blue
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("FOCAS EDU — LAST ATTEMPT KIT PRO")
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255) # White
        run.font.size = Pt(14)

        # EXAM TITLES
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        p_exam = doc.add_paragraph(f"{paper_level} EXAMINATION")
        p_exam.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_exam.add_run().bold = True
        p_exam.runs[0].font.size = Pt(13)
        
        p_sub = doc.add_paragraph(f"PAPER: {paper_subject}\nFULL TEST — {title_tag}")
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_sub.runs[0].bold = True
        p_sub.runs[0].font.size = Pt(11)

        # STATS ROW
        stats_table = doc.add_table(rows=1, cols=3)
        stats_table.width = Inches(7.2)
        stats_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        stats_table.style = 'Table Grid'
        stats_data = [f"Total Marks: {total_marks}", "Time: 3 Hours", "Date: _________"]
        for i, text in enumerate(stats_data):
            c = stats_table.rows[0].cells[i]
            set_cell_shading(c, "CFE2F3")
            c.text = text
            cp = c.paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cp.runs[0].bold = True
            cp.runs[0].font.size = Pt(10)

    # --- INSTRUCTIONS (Only for QP) ---
    qp_doc.add_paragraph().paragraph_format.space_after = Pt(4)
    inst_bar = qp_doc.add_table(rows=1, cols=1)
    inst_bar.width = Inches(7.2)
    inst_bar.alignment = WD_TABLE_ALIGNMENT.CENTER
    inst_cell = inst_bar.rows[0].cells[0]
    set_cell_shading(inst_cell, "FFF2CC") # Pale Yellow
    ip = inst_cell.paragraphs[0]
    ip.add_run("GENERAL INSTRUCTIONS:").bold = True
    for inst in ["1. All questions are COMPULSORY.", "2. Marks are indicated against each question in brackets [ ].", "3. Answers should be based on relevant Study Material and standards."]:
        p_inst = qp_doc.add_paragraph(inst)
        p_inst.style.font.size = Pt(9)
        p_inst.paragraph_format.left_indent = Inches(0.2)
        p_inst.paragraph_format.space_after = Pt(0)

    # --- PART BAR ---
    for doc in [qp_doc, ak_doc]:
        doc.add_paragraph().paragraph_format.space_after = Pt(6)
        part_table = doc.add_table(rows=1, cols=1)
        part_table.width = Inches(7.2)
        part_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        part_cell = part_table.rows[0].cells[0]
        set_cell_shading(part_cell, "002060") # Dark Blue
        pp = part_cell.paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_p = pp.add_run("PART — I")
        run_p.bold = True
        run_p.font.color.rgb = RGBColor(255, 255, 255)
        run_p.font.size = Pt(11)

    # 3. Retrieve and Format Questions & Answers
    questions_found = 0
    for index, row in df.iterrows():
        q_num = clean_val(row.get('question_number'))
        subject = clean_val(row.get('subject'))
        level = clean_val(row.get('level'))
        chapter = clean_val(row.get('chapter_number'))
        unit = clean_val(row.get('unit'))
        marks = clean_val(row.get('marks'))

        if not q_num: continue

        query = {
            "level": {"$regex": f"^{re.escape(level)}$", "$options": "i"},
            "subject": {"$regex": f"^{re.escape(subject)}$", "$options": "i"},
            "chapter": {"$regex": f"^{re.escape(chapter)}$", "$options": "i"},
            "question_no": {"$regex": f"^{re.escape(q_num)}$", "$options": "i"}
        }
        if unit: query["unit"] = {"$regex": f"^{re.escape(unit)}$", "$options": "i"}
            
        question_data = col.find_one(query)
        if question_data:
            questions_found += 1
            
            # --- PROCESS QUESTION (for QP) ---
            q_text = question_data.get("question_text", "")
            q_text_clean = clean_question_text(q_text)
            
            lines = q_text_clean.split('\n')
            first_text_line = ""
            remaining_lines = []
            has_first = False
            for line in lines:
                s = line.strip()
                if not has_first:
                    if not s: continue
                    if s.startswith('+') or s.startswith('|'):
                        remaining_lines.append(line)
                        has_first = True
                    else:
                        first_text_line = s + " "
                        has_first = True
                else: remaining_lines.append(line)

            head_table = qp_doc.add_table(rows=1, cols=2)
            head_table.autofit = False
            head_table.width = Inches(7.2)
            head_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            
            # Use explicit widths for each cell
            c_left = head_table.rows[0].cells[0]
            c_right = head_table.rows[0].cells[1]
            c_left.width = Inches(6.2)
            c_right.width = Inches(1.0)
            
            # Setup first paragraph in the cell
            p_head = c_left.paragraphs[0]
            p_head.paragraph_format.space_before = Pt(16) if questions_found > 1 else Pt(4)
            p_head.paragraph_format.left_indent = Inches(0.4)
            p_head.paragraph_format.first_line_indent = Inches(-0.4)
            
            run_q_label = p_head.add_run(f"Q{questions_found}. ")
            run_q_label.bold = True
            run_q_label.font.size = Pt(11)
            
            if first_text_line:
                # Add a space before body text to prevent "Q1.Beta"
                body_run = p_head.add_run(first_text_line.strip())
                body_run.font.size = Pt(10)

            # Keep remaining lines INSIDE the same cell for consistent alignment
            if remaining_lines:
                add_formatted_content(c_left, "\n".join(remaining_lines), left_indent=Inches(0.4))

            # Marks in the right cell
            p_marks = c_right.paragraphs[0]
            p_marks.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p_marks.paragraph_format.space_before = Pt(16) if questions_found > 1 else Pt(4)
            if marks:
                 m_val = str(marks).strip()
                 if '[' not in m_val and 'Mark' not in m_val: m_val = f"[{m_val} Marks]"
                 mk_run = p_marks.add_run(m_val)
                 mk_run.bold = True
                 mk_run.font.color.rgb = RGBColor(192, 0, 0)
                 mk_run.font.size = Pt(11)

            p_head.paragraph_format.space_after = Pt(2)

            # --- PROCESS ANSWER (for AK) ---
            ans_text = question_data.get("answer_text", "") or "No answer found in database."
            # Clean leading "Answer" keyword if it matches the pattern
            ans_text_clean = re.sub(r'^\s*Answer\s*\n*', '', ans_text, flags=re.IGNORECASE).strip()
            
            ak_head_p = ak_doc.add_paragraph()
            ak_head_p.paragraph_format.space_before = Pt(16) if questions_found > 1 else Pt(4)
            ak_head_run = ak_head_p.add_run(f"Answer to Q{questions_found}")
            ak_head_run.bold = True
            ak_head_run.font.size = Pt(11)
            ak_head_run.underline = True
            ak_head_p.paragraph_format.space_after = Pt(6)
            
            add_formatted_content(ak_doc, ans_text_clean)
            
        else:
            logger.warning(f"❌ Not found in DB: Q{q_num} (L={level}, S={subject}, Ch={chapter})")

    if questions_found == 0:
        return None  # Or raise exception here, handle in caller

    # 4. Save both to separate BytesIO
    qp_output = io.BytesIO()
    qp_doc.save(qp_output)
    qp_output.seek(0)
    
    ak_output = io.BytesIO()
    ak_doc.save(ak_output)
    ak_output.seek(0)
    
    # 5. Create ZIP package
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("01_Question_Paper.docx", qp_output.getvalue())
        zip_file.writestr("02_Answer_Key.docx", ak_output.getvalue())
    
    zip_buffer.seek(0)
    return zip_buffer
