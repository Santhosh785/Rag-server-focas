from pdfminer.high_level import extract_text

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
try:
    text = extract_text(pdf_path)
    print(f"Extracted length: {len(text)}")
    print(f"Preview: {text[:100]}")
except Exception as e:
    print(f"Error: {e}")
