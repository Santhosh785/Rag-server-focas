import re
import pdfplumber
import os

def extract_page_content(page):
    # Simplified version for debugging
    return page.extract_text() or ""

def split_q_and_a(body: str) -> tuple[str, str]:
    patterns = [
        r'\b(?:ANSWER|Answer|SOLUTION|Solution|Soln?|Suggested\s+Answer)\s*:',
        r'^\s*(?:ANSWER|Answer|SOLUTION|Solution|Soln?|Suggested\s+Answer)\s*$',
        r'^\s*(?:ANSWER|Answer|SOLUTION|Solution|Soln?)\b',
        r'^Working Notes?\s*$',
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE | re.MULTILINE)
        if m:
            return body[:m.start()].strip(), body[m.start():].strip()
    return body.strip(), ""

def debug_file(pdf_path):
    print(f"\n--- Debugging {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join([p.extract_text() or "" for p in pdf.pages])
    
    pattern = re.compile(
        r'(\b(?:QUESTION|Question|Q\.?)\s*(?:NO\.?|No\.?)?\s*\d+)',
        re.IGNORECASE | re.MULTILINE
    )
    splits = pattern.split(text)
    
    i = 1
    while i < len(splits) - 1:
        header    = splits[i].strip()
        body      = splits[i + 1].strip()
        
        num_match = re.search(r'\d+', header)
        q_num     = num_match.group() if num_match else "?"
        
        q_text, a_text = split_q_and_a(body)
        
        if not a_text:
            print(f"FAILED: Q{q_num} (Header: {header})")
            print(f"BODY START: {repr(body[:300])}")
            print("-" * 40)
        i += 2

debug_file('pdfs/Intermediate/FM/Chapter_2_TYPES OF FINANCING.pdf')
debug_file('pdfs/Intermediate/FM/Chapter_3_RATIO_ANALYSIS.pdf')
