import io
import subprocess
import zipfile
from types import SimpleNamespace

import pytest
from docx import Document
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from resume_tailor import documents


def pdf_bytes():
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(50, 750, 'Avery Example - Software Engineer')
    page.drawString(50, 730, 'Built reliable Java services and improved response times.')
    page.save()
    return output.getvalue()


def docx_bytes():
    document = Document()
    document.sections[0].header.paragraphs[0].text = 'Avery Example'
    document.sections[0].different_first_page_header_footer = True
    document.sections[0].first_page_header.paragraphs[0].text = 'avery@example.com'
    document.add_heading('Experience', level=1)
    document.add_paragraph('Built reliable Java services for customers.')
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = 'Python'
    table.cell(0, 1).text = 'SQL'
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


@pytest.mark.parametrize('filename,content,expected', [
    ('resume.pdf', pdf_bytes(), 'Built reliable Java services'),
    ('resume.docx', docx_bytes(), 'Python'),
])
def test_extracts_supported_resumes_in_an_isolated_worker(filename, content, expected):
    result = documents.parse_resume(filename, content)
    assert expected in result.text
    assert result.warnings
    if filename.endswith('.docx'):
        assert 'Avery Example' in result.text and 'avery@example.com' in result.text and 'SQL' in result.text
        assert result.text.index('Experience') < result.text.index('Python')


@pytest.mark.parametrize('filename,content', [
    ('resume.pdf', b'not a PDF'),
    ('resume.docx', b'not a Word file'),
    ('resume.txt', b'plain text'),
    ('resume.pdf', docx_bytes()),
    ('resume.pdf', b'x' * (5_000_000 + 1)),
])
def test_rejects_invalid_type_or_size(filename, content):
    with pytest.raises(documents.DocumentError):
        documents.parse_resume(filename, content)


def test_rejects_encrypted_or_scanned_pdfs():
    reader = PdfReader(io.BytesIO(pdf_bytes()))
    writer = PdfWriter()
    writer.append(reader)
    writer.encrypt('example-password')
    encrypted = io.BytesIO()
    writer.write(encrypted)
    with pytest.raises(documents.DocumentError, match='encrypted|locked'):
        documents.parse_resume('resume.pdf', encrypted.getvalue())
    blank = PdfWriter()
    blank.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    blank.write(output)
    with pytest.raises(documents.DocumentError, match='text|scanned'):
        documents.parse_resume('resume.pdf', output.getvalue())


def test_rejects_docx_with_macros_or_excessive_expansion():
    macro = io.BytesIO(docx_bytes())
    with zipfile.ZipFile(macro, 'a') as archive:
        archive.writestr('word/vbaProject.bin', b'fake macro')
    with pytest.raises(documents.DocumentError, match='macro'):
        documents.parse_resume('resume.docx', macro.getvalue())
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', b'a' * (25_000_000 + 1))
    with pytest.raises(documents.DocumentError, match='large|size'):
        documents.parse_resume('resume.docx', bomb.getvalue())


def test_worker_timeout_is_reported_without_leaking_content(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd='worker', timeout=1)
    monkeypatch.setattr(documents.subprocess, 'run', timeout)
    with pytest.raises(documents.DocumentError, match='too long') as exc:
        documents.parse_resume('resume.pdf', pdf_bytes())
    assert 'Avery' not in str(exc.value)


def test_worker_does_not_inherit_provider_keys(monkeypatch):
    def run(*args, **kwargs):
        assert 'OPENAI_API_KEY' not in kwargs['env']
        return SimpleNamespace(returncode=0, stdout=b'{"text":"Example resume text for testing.","warnings":[]}')
    monkeypatch.setenv('OPENAI_API_KEY', 'dummy-secret-never-real')
    monkeypatch.setattr(documents.subprocess, 'run', run)
    assert 'Example resume' in documents.parse_resume('resume.pdf', pdf_bytes()).text


def test_word_external_entities_are_not_read(tmp_path):
    secret = tmp_path / 'private-example.txt'
    secret.write_text('PRIVATE_TEST_SENTINEL', encoding='utf-8')
    source = io.BytesIO(docx_bytes())
    output = io.BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as changed:
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename == 'word/document.xml':
                xml = content.decode('utf-8')
                declaration, body = xml.split('?>', 1)
                xml = declaration + '?>\n<!DOCTYPE document [<!ENTITY xxe SYSTEM "' + secret.as_uri() + '">]>' + body
                content = xml.replace('Built reliable Java services for customers.', '&xxe;').encode('utf-8')
            changed.writestr(item.filename, content)
    try:
        result = documents.parse_resume('resume.docx', output.getvalue())
    except documents.DocumentError:
        return
    assert 'PRIVATE_TEST_SENTINEL' not in result.text
