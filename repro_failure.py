from ingest import extract_pdf, chunk_by_question, split_q_and_a
import os

pdf2 = 'pdfs/Intermediate/FM/Chapter_2_TYPES OF FINANCING.pdf'
pdf3 = 'pdfs/Intermediate/FM/Chapter_3_RATIO_ANALYSIS.pdf'

def test_file(path):
    print(f"\nTesting {path}...")
    text = extract_pdf(path)
    chunks = chunk_by_question(text)
    for c in chunks:
        if not c['answer_text']:
            print(f"FAILED: Q{c['question_no']}")
            # Find the header in the content to print context
            print(f"FULL CONTENT SLICE: {repr(c['content'][:300])}")

test_file(pdf2)
test_file(pdf3)
