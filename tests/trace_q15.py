import re
import pdfplumber

def split_q_and_a(body):
    patterns = [
        r'\b(?:ANSWER|Answer|SOLUTION|Solution|Soln?|Suggested\s+Answer)\s*:',
        r'^\s*(?:ANSWER|Answer|SOLUTION|Solution|Soln?|Suggested\s+Answer)\s*$',
        r'^\s*(?:ANSWER|Answer|SOLUTION|Solution|Soln?)\b',
        r'^Working Notes?\s*$',
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE | re.MULTILINE)
        if m:
            print(f"Matched pattern: {pat}")
            print(f"Split at index: {m.start()}")
            print(f"Text around split: {repr(body[max(0, m.start()-20):m.end()+20])}")
            return body[:m.start()].strip(), body[m.start():].strip()
    return body.strip(), ""

pdf_path = 'pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf'
with pdfplumber.open(pdf_path) as pdf:
    text = "\n".join([p.extract_text() or "" for p in pdf.pages])

pattern = re.compile(r'(\b(?:QUESTION|Question|Q\.?)\s*(?:NO\.?|No\.?)?\s*\d+)', re.MULTILINE)
splits = pattern.split(text)

i = 1
while i < len(splits) - 1:
    header = splits[i].strip()
    body = splits[i+1].strip()
    if "15" in header:
        print(f"--- Processing {header} ---")
        q_text, a_text = split_q_and_a(body)
        print(f"Final Q: {repr(q_text[:100])}...")
        print(f"Final A: {repr(a_text[:100])}...")
    i += 2
