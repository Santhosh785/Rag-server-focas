import pdfplumber

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
with pdfplumber.open(pdf_path) as pdf:
    p = pdf.pages[0]
    print(f"Page size: {p.width} x {p.height}")
    print(f"Bbox: {p.bbox}")
