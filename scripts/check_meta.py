import pdfplumber

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
try:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Metadata: {pdf.metadata}")
        print(f"Is Encrypted: {pdf.doc.is_encrypted if hasattr(pdf.doc, 'is_encrypted') else 'Unknown'}")
        for i in range(min(5, len(pdf.pages))):
             p = pdf.pages[i]
             print(f"Page {i+1} chars: {len(p.chars)}")
except Exception as e:
    print(f"Error: {e}")
