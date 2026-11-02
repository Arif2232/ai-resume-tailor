import io

import pytest
from docx import Document
from pypdf import PdfReader

from resume_tailor.exports import ExportError, render_docx, render_pdf


TEXT = ('Avery Example\navery@example.com\n\nSUMMARY\nBackend engineer with experience in Java and SQL.\n\n'
        'EXPERIENCE\nEngineer at ExampleCo, 2020 to 2024\n- Built reliable services for customers.\n\n'
        'SKILLS\nJava, SQL, Python\n\nEDUCATION\nBachelor of Engineering')


def test_pdf_and_word_preserve_reviewed_text_in_reading_order():
    pdf = render_pdf(TEXT)
    docx = render_docx(TEXT)
    pdf_text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    document = Document(io.BytesIO(docx))
    word_text = '\n'.join(p.text for p in document.paragraphs)
    for output in (pdf_text, word_text):
        assert output.index('Avery Example') < output.index('SUMMARY') < output.index('EXPERIENCE')
        assert output.index('ExampleCo') < output.index('SKILLS') < output.index('EDUCATION')
        assert 'Built reliable services' in output and 'Java, SQL, Python' in output
    assert not document.core_properties.author


def test_pdf_renders_common_international_symbols_without_losing_them():
    text = 'José Example\njose@example.com\n\nEXPERIENCE\nManaged a ₹5,000 budget.'
    output = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(render_pdf(text))).pages)
    assert 'José Example' in output and '₹5,000' in output


def test_long_resume_retains_all_lines_across_pdf_pages_and_word():
    lines = ['Avery Example', 'avery@example.com', 'EXPERIENCE'] + [
        f'- Worked on project {i} with Java and SQL for a customer-facing platform.' for i in range(1, 101)
    ]
    text = '\n'.join(lines)
    reader = PdfReader(io.BytesIO(render_pdf(text)))
    assert len(reader.pages) > 1
    outputs = [' '.join(' '.join(page.extract_text().split()) for page in reader.pages),
               ' '.join(' '.join(p.text.split()) for p in Document(io.BytesIO(render_docx(text))).paragraphs)]
    for output in outputs:
        for line in lines:
            assert ' '.join(line.split()) in output


def test_unsupported_pdf_script_fails_clearly_instead_of_corrupting_text():
    text = 'Avery Example\navery@example.com\n\nEXPERIENCE\nअनुभव और कौशल'
    with pytest.raises(ExportError, match='Word|DOCX'):
        render_pdf(text)
    assert 'अनुभव' in '\n'.join(p.text for p in Document(io.BytesIO(render_docx(text))).paragraphs)


@pytest.mark.parametrize('text', ['', 'x' * 50_001, 'Valid name\x00 with an invalid control character'])
def test_invalid_export_content_is_rejected(text):
    with pytest.raises(ExportError):
        render_pdf(text)
