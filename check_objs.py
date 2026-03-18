import pdfplumber

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
with pdfplumber.open(pdf_path) as pdf:
    for i in range(min(3, len(pdf.pages))):
        page = pdf.pages[i]
        print(f"Page {i+1}:")
        print(f"  Chars: {len(page.chars)}")
        print(f"  Rects: {len(page.objects.get('rect', []))}")
        print(f"  Lines: {len(page.objects.get('line', []))}")
        print(f"  Curves: {len(page.objects.get('curve', []))}")
        print(f"  Images: {len(page.objects.get('image', []))}")
