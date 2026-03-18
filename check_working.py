import pdfplumber

pdf_path = "pdfs/Final/FM/Chapter_3_RATIO_ANALYSIS.pdf"
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    print(f"File: {pdf_path}")
    print(f"Object keys: {page.objects.keys()}")
    for k, v in page.objects.items():
        print(f"  {k}: {len(v)}")
    layout = page.layout
    print(f"Layout objects: {len(layout)}")
