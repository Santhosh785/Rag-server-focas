import pdfplumber

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages):
        print(f"Page {i+1}: Chars={len(page.chars)}, Images={len(page.images)}, Curves={len(page.objects.get('curve', []))}")
