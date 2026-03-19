import re
import pdfplumber

def debug_file(pdf_path):
    print(f"\n--- Debugging {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join([p.extract_text() or "" for p in pdf.pages])
    
    print(f"Text length: {len(text)}")
    
    # EXACT regex from ingest.py
    pattern = re.compile(
        r'(\b(?:QUESTION|Question|Q\.?)\s*(?:NO\.?|No\.?)?\s*\d+)',
        re.MULTILINE
    )
    
    matches = pattern.findall(text)
    print(f"Matches found: {len(matches)}")
    if matches:
        print(f"First match: {matches[0]}")
    
    splits = pattern.split(text)
    print(f"Splits: {len(splits)}")

debug_file('pdfs/Intermediate/FM/Chapter_2_TYPES OF FINANCING.pdf')
debug_file('pdfs/Intermediate/FM/Chapter_3_RATIO_ANALYSIS.pdf')
