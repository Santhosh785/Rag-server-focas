import pdfplumber

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    print(f"Object keys: {page.objects.keys()}")
    for k, v in page.objects.items():
        print(f"  {k}: {len(v)}")
    
    # Check underlying pdfminer layout
    layout = page.layout
    print(f"Layout objects: {len(layout)}")
    for obj in layout:
         print(f"  - {type(obj)}")
