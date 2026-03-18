import pdfplumber

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    print(f"Images on page 1: {len(page.images)}")
    print(f"Objects on page 1: {page.objects.keys()}")
    if 'image' in page.objects:
         print(f"Total image objects: {len(page.objects['image'])}")
