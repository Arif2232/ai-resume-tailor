"""Validate uploads and extract their text without keeping the file."""

import json
import os
import subprocess
import sys
from dataclasses import dataclass

MAX_UPLOAD_BYTES = 5_000_000
MAX_TEXT_CHARS = 50_000
WORKER_TIMEOUT = 15


class DocumentError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedResume:
    text: str
    warnings: list[str]


def parse_resume(filename: str, content: bytes) -> ParsedResume:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise DocumentError('Choose a resume smaller than 5 MB.')
    name = (filename or '').lower()
    if name.endswith('.pdf') and content.startswith(b'%PDF-'):
        kind = 'pdf'
    elif name.endswith('.docx') and content.startswith(b'PK\x03\x04'):
        kind = 'docx'
    else:
        raise DocumentError('Choose a valid PDF or DOCX resume.')

    allowed_env = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP', 'TMPDIR', 'LANG', 'LC_ALL')
    env = {name: os.environ[name] for name in allowed_env if name in os.environ}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-I', '-m', 'resume_tailor.document_worker', kind], input=content,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=WORKER_TIMEOUT, env=env, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DocumentError('Reading the resume took too long. Try a simpler file.') from exc
    except OSError as exc:
        raise DocumentError('Could not start the resume reader. Try again.') from exc
    if result.returncode != 0 or len(result.stdout) > 1_000_000:
        raise DocumentError('The resume could not be read. Try another file.')
    try:
        output = json.loads(result.stdout)
        if output.get('error'):
            raise DocumentError(output['error'])
        text, warnings = output['text'], output['warnings']
        if not isinstance(text, str) or not isinstance(warnings, list) or len(text) > MAX_TEXT_CHARS:
            raise ValueError('Invalid worker response')
        return ParsedResume(text=text, warnings=warnings)
    except DocumentError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise DocumentError('The resume could not be read. Try another file.') from exc
