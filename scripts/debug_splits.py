import re
import pdfplumber

def extract_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join([p.extract_text() or "" for p in pdf.pages])

pdf_path = 'pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf'
text = extract_pdf(pdf_path)

pattern = re.compile(
    r'(\b(?:QUESTION|Question|Q\.?)\s*(?:NO\.?|No\.?)?\s*\d+)',
    re.MULTILINE
)

matches = pattern.findall(text)
print(f"Found {len(matches)} matches:")
for m in matches:
    print(f"  - {m}")

splits = pattern.split(text)
print(f"Number of splits: {len(splits)}")
