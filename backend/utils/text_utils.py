import pandas as pd
import re

def clean_val(val):
    if pd.isna(val): return ""
    if isinstance(val, (float, int)):
        if float(val).is_integer(): return str(int(val))
        return str(val)
    return str(val).strip()

def clean_question_text(q_text: str) -> str:
    """Removes leading question numbers and metadata blocks."""
    # 1. Remove "Question No. X" headers
    q_text_clean = re.sub(r'^\s*(?:QUESTION|Question)\s+(?:NO\.?\s+)?\d+[^\n]*\n', '', q_text, flags=re.IGNORECASE).strip()
    
    # 2. Exhaustively remove all leading metadata blocks (e.g. (MTP...), [RTP...], (PYP...))
    while True:
        # Matches anything starting with ( or [ and ending with ) or ] at the beginning
        meta_match = re.match(r'^([\[\(].*?[\]\)])\s*', q_text_clean, flags=re.IGNORECASE)
        if meta_match:
            content = meta_match.group(1).upper()
            # If it contains typical metadata keywords, remove it
            keywords = ["MTP", "RTP", "PYP", "MARK", "MAY", "NOV", "OCT", "APR", "20"]
            if any(k in content for k in keywords):
                q_text_clean = q_text_clean[meta_match.end():].strip()
                continue
        break
    return q_text_clean
