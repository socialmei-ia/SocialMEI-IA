"""Private Linux PDF extraction worker. Bounded stdin/stdout; no network or document execution."""
import io
import json
import re
import sys

MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 100
MAX_CHUNKS = 500
MAX_CHARACTERS = 500000


def limits():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024, 192 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def extract(raw):
    from pypdf import PdfReader
    pdf = PdfReader(io.BytesIO(raw), strict=True)
    root = pdf.trailer['/Root']
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= MAX_PAGES:
        raise ValueError()
    if '/OpenAction' in root or '/AA' in root:
        raise ValueError()
    names = root.get('/Names')
    if names:
        names = names.get_object()
        if '/JavaScript' in names or '/EmbeddedFiles' in names:
            raise ValueError()
    chunks, total = [], 0
    for page_number, page in enumerate(pdf.pages, 1):
        if '/AA' in page:
            raise ValueError()
        for reference in page.get('/Annots', []):
            annotation = reference.get_object()
            if any(key in annotation for key in ('/A','/AA','/FS')):
                raise ValueError()
        text = page.extract_text() or ''
        total += len(text)
        if total > MAX_CHARACTERS:
            raise ValueError()
        text = ''.join(char for char in re.sub(r'\s+',' ',text).strip() if char.isprintable())
        start = 0
        while start < len(text):
            part = text[start:start+950].strip()
            if part:
                chunks.append((len(chunks),page_number,part))
            if len(chunks) > MAX_CHUNKS:
                raise ValueError()
            if start+950 >= len(text):
                break
            start += 850
    return len(pdf.pages), chunks


def main():
    # Apply OS limits before importing the parser or reading untrusted bytes.
    limits()
    raw = sys.stdin.buffer.read(MAX_BYTES+1)
    if not 8 <= len(raw) <= MAX_BYTES or not raw.startswith(b'%PDF-'):
        return 1
    try:
        result = extract(raw)
    except Exception:
        return 1
    sys.stdout.write(json.dumps(result,ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
