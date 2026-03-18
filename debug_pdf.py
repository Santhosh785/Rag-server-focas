import pdfplumber
import os

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
print(f"Checking {pdf_path}...")

if not os.path.exists(pdf_path):
    print("File not found!")
else:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Total pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            words = page.extract_words()
            tables = page.extract_tables()
            print(f"Page {i+1}:")
            print(f"  Text length: {len(text) if text else 0}")
            print(f"  Words count: {len(words)}")
            print(f"  Tables count: {len(tables)}")
            if text:
                print(f"  Snippet: {text[:200]}...")
            if i == 0: # Only check first page
                break
