"""Bounded, isolated resume text extraction; input and output stay in memory."""

import io
import json
import sys
import zipfile

from resume_tailor.documents import DocumentError, MAX_TEXT_CHARS, MAX_UPLOAD_BYTES

MAX_DOCX_EXPANDED = 25_000_000
MAX_DOCX_ENTRIES = 500
MAX_PAGES = 12


def limit_resources():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (12, 13))
        if sys.platform.startswith('linux'):
            resource.setrlimit(resource.RLIMIT_AS, (1_073_741_824, 1_073_741_824))
    except (ImportError, OSError, ValueError):
        pass


def validate_docx(content: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > MAX_DOCX_ENTRIES or sum(entry.file_size for entry in entries) > MAX_DOCX_EXPANDED:
                raise DocumentError('The Word file is too large to read safely.')
            if len(set(names)) != len(names) or any(entry.flag_bits & 1 for entry in entries):
                raise DocumentError('The Word file is locked or malformed.')
            if any('vbaproject.bin' in name.casefold() for name in names):
                raise DocumentError('Word files containing macros are not supported.')
            if any('..' in name.replace('\\', '/').split('/') for name in names):
                raise DocumentError('The Word file contains an unsafe entry.')
            if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                raise DocumentError('Choose a valid DOCX resume.')
    except (zipfile.BadZipFile, OSError) as exc:
        raise DocumentError('The Word file could not be read.') from exc


def docx_text(content: bytes) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    validate_docx(content)
    document = Document(io.BytesIO(content))

    def blocks(container):
        for block in container.iter_inner_content():
            if isinstance(block, Paragraph):
                if block.text.strip():
                    yield block.text.strip()
            elif isinstance(block, Table):
                for row in block.rows:
                    seen = set()
                    for cell in row.cells:
                        if cell._tc not in seen:
                            seen.add(cell._tc)
                            yield from blocks(cell)

    headers, footers, seen = [], [], set()
    for section in document.sections:
        parts = [(section.header, headers), (section.footer, footers)]
        if section.different_first_page_header_footer:
            parts.extend([(section.first_page_header, headers), (section.first_page_footer, footers)])
        if document.settings.odd_and_even_pages_header_footer:
            parts.extend([(section.even_page_header, headers), (section.even_page_footer, footers)])
        for part, output in parts:
            name = str(part.part.partname)
            if name not in seen:
                seen.add(name)
                output.extend(blocks(part))
    return '\n'.join([*headers, *blocks(document), *footers])


def pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        raise DocumentError('Choose an unlocked, unencrypted PDF resume.')
    if not 1 <= len(reader.pages) <= MAX_PAGES:
        raise DocumentError('Choose a PDF with at most 12 pages.')
    return '\n'.join(page.extract_text() or '' for page in reader.pages)


def main():
    limit_resources()
    try:
        content = sys.stdin.buffer.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES or len(sys.argv) != 2:
            raise DocumentError('The resume is too large to read safely.')
        text = pdf_text(content) if sys.argv[1] == 'pdf' else docx_text(content)
        text = text.replace('\x00', '').strip()
        if len(text) < 20:
            raise DocumentError('No readable text was found. Scanned PDFs need selectable text or a text version.')
        if len(text) > MAX_TEXT_CHARS:
            raise DocumentError('The resume text is too large. Try a shorter document.')
        warnings = ['Check the extracted text for missing sections, dates, tables, or layout changes.']
        print(json.dumps({'text': text, 'warnings': warnings}))
    except DocumentError as exc:
        print(json.dumps({'error': str(exc)}))
    except Exception:
        print(json.dumps({'error': 'The resume could not be read. Try another file.'}))


if __name__ == '__main__':
    main()
