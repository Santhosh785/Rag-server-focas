import re

body = """ [RTP May 23]
HIGHLIGHT the similarities and differences between Samurai Bond and Bull Dog Bond.
Answer
Samurai bonds are denominated in Japanese Yen JPY
Issued in Tokyo"""

def split_q_and_a(body: str):
    patterns = [
        r'\b(?:ANSWER|Answer|SOLUTION|Solution|Soln?|Suggested\s+Answer)\s*:',
        r'^\s*(?:ANSWER|Answer|SOLUTION|Solution|Soln?|Suggested\s+Answer)\s*$',
        r'^\s*(?:ANSWER|Answer|SOLUTION|Solution|Soln?)\b',
        r'^Working Notes?\s*$',
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE | re.MULTILINE)
        if m:
            print(f"Matched pattern: {pat}")
            return body[:m.start()].strip(), body[m.start():].strip()
    return body.strip(), ""

q, a = split_q_and_a(body)
print(f"Q: {repr(q)}")
print(f"A: {repr(a)}")
