"""
PII / private data filter for real estate scraped data.
Removes phone numbers, email addresses, personal names, and other PII
from all text fields before storage.
"""

import re

# Hungarian phone patterns: +36 20 123 4567, 06 20 123 4567, 06/20/123-4567, etc.
PHONE_PATTERNS = [
    re.compile(r'(\+36|06|0036)[\s/-]?\d{2}[\s/-]?\d{3,4}[\s/-]?\d{3,4}'),
    re.compile(r'\b\d{2}[\s/-]\d{3,4}[\s/-]\d{3,4}\b'),  # generic local format
    re.compile(r'\b\d{8,11}\b(?=\s*(Ft|EUR|forint|euro|HUF))'),  # bare numbers near currency
]

# Email pattern
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Lines that are purely contact info — detected by keyword at start of line
PII_LINE_PREFIXES = [
    'telefon:', 'tel:', 'telefon ', 'mobil:', 'mobile:', 'phone:',
    'e-mail:', 'email:', 'e-mail cím:', 'email cím:', 'e-mail cím ', 'email cím ',
    'kapcsolat:', 'kapcsolat ',
    'cím:', 'cím ', 'székhely:', 'székhely ',
    'adószám:', 'adószám ', 'bankszámla:', 'bankszámla ', 'iban:', 'iban ',
    'hívjon:', 'hívjon ', 'call me:',
    'személyes:', 'személyes ',
]


def _is_pii_only_line(line: str) -> bool:
    """Check if a line is purely a contact-info line (not a property description)."""
    lower = line.lower().strip()
    if not lower:
        return False
    return any(lower.startswith(prefix) for prefix in PII_LINE_PREFIXES)


def scrub_text(text: str) -> str:
    """Remove PII from a text field. Returns cleaned text."""
    if not text:
        return text

    # Remove lines that are purely contact info
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if _is_pii_only_line(line):
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    # Remove emails
    text = EMAIL_PATTERN.sub('[email]', text)

    # Remove phone numbers
    for pat in PHONE_PATTERNS:
        text = pat.sub('[telefon]', text)

    # Collapse multiple spaces/newlines
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def scrub_record(record: dict) -> dict:
    """Scrub all text fields in a listing record for PII."""
    text_fields = ['title', 'description', 'location_raw', 'city', 'district']
    for field in text_fields:
        if field in record and isinstance(record[field], str):
            record[field] = scrub_text(record[field])

    # Ensure raw_data never contains PII keys
    if 'raw_data' in record and isinstance(record['raw_data'], str):
        try:
            import json
            data = json.loads(record['raw_data'])
            pii_keys = {'seller_name', 'seller_phone', 'phone', 'email', 'name',
                        'address', 'contact', 'company_name', 'indiv_name'}
            for k in list(data.keys()):
                if k.lower() in pii_keys:
                    del data[k]
            record['raw_data'] = json.dumps(data, ensure_ascii=False)
        except (ValueError, TypeError):
            pass  # not valid JSON, leave as-is

    # Remove seller_name if present (shouldn't be stored)
    record.pop('seller_name', None)

    return record
