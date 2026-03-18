import pypdf
import os

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
print(f"Checking with pypdf: {pdf_path}")

try:
    reader = pypdf.PdfReader(pdf_path)
    print(f"Total pages: {len(reader.pages)}")
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        print(f"Page {i+1} text length: {len(text) if text else 0}")
        if text and len(text.strip()) > 0:
            print(f"  Snippet: {text[:200]}")
        if i == 1: break # Check first two pages
except Exception as e:
    print(f"Error: {e}")
