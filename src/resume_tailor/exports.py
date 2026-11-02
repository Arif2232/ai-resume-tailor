"""Create simple, single-column PDF and Word resumes from reviewed text."""

import io
import threading
import unicodedata
from html import escape
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt, RGBColor
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

MAX_EXPORT_CHARS = 50_000
HEADINGS = {'SUMMARY', 'SKILLS', 'EXPERIENCE', 'PROJECTS', 'EDUCATION', 'CERTIFICATIONS',
            'AWARDS', 'LANGUAGES', 'VOLUNTEER', 'PUBLICATIONS', 'OTHER'}
FONT_DIR = Path(__file__).resolve().parent / 'assets' / 'fonts'
FONT_LOCK = threading.Lock()


class ExportError(ValueError):
    pass


def validated_text(text: str) -> str:
    if not isinstance(text, str) or not 20 <= len(text.strip()) <= MAX_EXPORT_CHARS:
        raise ExportError('Enter a resume between 20 and 50,000 characters.')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in text):
        raise ExportError('The resume contains an unsupported control character.')
    return text.replace('\r\n', '\n').replace('\r', '\n').strip()


def register_fonts():
    with FONT_LOCK:
        if 'ResumeSans' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('ResumeSans', str(FONT_DIR / 'DejaVuSans.ttf')))
        if 'ResumeSans-Bold' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('ResumeSans-Bold', str(FONT_DIR / 'DejaVuSans-Bold.ttf')))
    return pdfmetrics.getFont('ResumeSans')


def render_pdf(text: str) -> bytes:
    text = unicodedata.normalize('NFC', validated_text(text))
    try:
        font = register_fonts()
        bold_font = pdfmetrics.getFont('ResumeSans-Bold')
        for char in text:
            if char in '\n\r\t':
                continue
            if (ord(char) > 0xFFFF or unicodedata.bidirectional(char) in ('R', 'AL', 'AN')
                    or unicodedata.combining(char) or ord(char) not in font.face.charWidths
                    or ord(char) not in bold_font.face.charWidths):
                raise ExportError('Some characters cannot be rendered safely in PDF yet. Download the Word (DOCX) file instead.')
        output = io.BytesIO()
        name_style = ParagraphStyle('name', fontName='ResumeSans-Bold', fontSize=17, leading=22,
                                    textColor=colors.HexColor('#1f2937'), spaceAfter=7)
        heading_style = ParagraphStyle('heading', fontName='ResumeSans-Bold', fontSize=10.5, leading=15,
                                       textColor=colors.HexColor('#1f2937'), spaceBefore=8, spaceAfter=4,
                                       keepWithNext=True)
        body_style = ParagraphStyle('body', fontName='ResumeSans', fontSize=10, leading=14, spaceAfter=4,
                                    splitLongWords=True)
        document = SimpleDocTemplate(output, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=45, bottomMargin=45,
                                     title='Resume', author='')
        story = []
        first = True
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 3))
                continue
            style = name_style if first else heading_style if line.upper() in HEADINGS else body_style
            story.append(Paragraph(escape(line), style))
            first = False
        document.build(story)
        result = output.getvalue()
        if len(PdfReader(io.BytesIO(result)).pages) > 12:
            raise ExportError('The resume is too long for PDF. Shorten it and try again.')
        return result
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError('Could not create the PDF. Try the Word file or shorten the resume.') from exc


def render_docx(text: str) -> bytes:
    text = validated_text(text)
    try:
        document = Document()
        section = document.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.top_margin = section.bottom_margin = Cm(1.6)
        section.left_margin = section.right_margin = Cm(1.8)
        normal = document.styles['Normal']
        normal.font.name, normal.font.size = 'Arial', Pt(10.5)
        normal.paragraph_format.space_after = Pt(4)
        normal.paragraph_format.line_spacing = 1.1
        heading = document.styles['Heading 1']
        heading.font.name, heading.font.size = 'Arial', Pt(11)
        heading.font.color.rgb = RGBColor.from_string('1F2937')
        heading.paragraph_format.space_before, heading.paragraph_format.space_after = Pt(8), Pt(4)
        first = True
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if first:
                paragraph = document.add_paragraph()
                run = paragraph.add_run(line)
                run.bold, run.font.size = True, Pt(17)
                first = False
            elif line.upper() in HEADINGS:
                document.add_paragraph(line, style='Heading 1')
            else:
                document.add_paragraph(line)
        document.core_properties.author = ''
        document.core_properties.last_modified_by = ''
        document.core_properties.title = 'Resume'
        document.core_properties.subject = ''
        document.core_properties.comments = ''
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()
    except Exception as exc:
        raise ExportError('Could not create the Word file. Try again.') from exc
