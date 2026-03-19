from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument

pdf_path = "pdfs/Final/FM/Chapter_1_SCOPE & OBJECTIVE OF FM.pdf"
with open(pdf_path, 'rb') as fp:
    parser = PDFParser(fp)
    doc = PDFDocument(parser)
    print(f"Is extractable: {doc.is_extractable}")
    print(f"Is encryption: {doc.encryption is not None}")
