"""Local-only HTTP interface; candidate documents and keys are not persisted."""

import asyncio
import hmac
import secrets
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from resume_tailor import documents, exports, job_urls, providers

WEB = Path(__file__).resolve().parent / 'web'
TOKEN = secrets.token_urlsafe(32)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])
app.mount('/assets', StaticFiles(directory=WEB), name='assets')
PARSE_SLOTS = asyncio.Semaphore(2)
AI_SLOTS = asyncio.Semaphore(2)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProviderInput(StrictInput):
    provider: Literal['openai', 'gemini', 'claude']
    model: str = Field(default='', max_length=128)
    api_key: SecretStr
    workspace_id: str = Field(default='', max_length=128)


class TailorInput(ProviderInput):
    resume: str = Field(min_length=20, max_length=50_000)
    job_description: str = Field(min_length=50, max_length=30_000)
    consent: bool = False

    @field_validator('resume', 'job_description')
    @classmethod
    def check_text(cls, value):
        value = value.strip()
        if any(ord(char) < 32 and char not in '\n\r\t' for char in value):
            raise ValueError('Text contains unsupported control characters.')
        return value


class JobInput(StrictInput):
    url: str = Field(min_length=1, max_length=4096)


class ExportInput(StrictInput):
    text: str = Field(min_length=20, max_length=50_000)
    format: Literal['pdf', 'docx']
    confirmed: bool = False


def verify_token(value: str | None):
    if not value or len(value) > 128 or not value.isascii() or not hmac.compare_digest(value, TOKEN):
        raise HTTPException(status_code=403, detail='Refresh the page and try again.')


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse({'detail': 'Please check the form and try again.'}, status_code=400)


@app.middleware('http')
async def security_headers(request: Request, call_next):
    limits = {'/api/resume': 5_000_000, '/api/job-url': 10_000, '/api/test-provider': 10_000,
              '/api/tailor': 600_000, '/api/export': 300_000}
    response = None
    if request.method == 'POST' and request.url.path in limits:
        length = request.headers.get('content-length')
        if length is None:
            response = JSONResponse({'detail': 'A content length is required.'}, status_code=411)
        elif len(length) > 10 or not length.isascii() or not length.isdecimal():
            response = JSONResponse({'detail': 'Invalid request.'}, status_code=400)
        elif int(length) > limits[request.url.path]:
            response = JSONResponse({'detail': 'The request is too large.'}, status_code=413)
    if response is None:
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse({'detail': 'Something went wrong. Please try again.'}, status_code=500)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    return response


@app.get('/', response_class=HTMLResponse)
async def index():
    return (WEB / 'index.html').read_text(encoding='utf-8').replace('__APP_TOKEN__', TOKEN)


@app.get('/api/options')
async def options(x_app_token: str | None = Header(default=None)):
    verify_token(x_app_token)
    return {name: {key: value for key, value in config.items() if key != 'url'}
            for name, config in providers.PROVIDERS.items()}


@app.post('/api/resume')
async def upload_resume(request: Request, x_resume_filename: str = Header(default=''),
                        x_app_token: str | None = Header(default=None)):
    verify_token(x_app_token)
    if len(x_resume_filename) > 255:
        raise HTTPException(status_code=400, detail='Choose a PDF or DOCX resume.')
    try:
        async with PARSE_SLOTS:
            parsed = await asyncio.to_thread(documents.parse_resume, x_resume_filename, await request.body())
        return {'text': parsed.text, 'warnings': parsed.warnings}
    except documents.DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/job-url')
async def import_job(data: JobInput, x_app_token: str | None = Header(default=None)):
    verify_token(x_app_token)
    try:
        text = await job_urls.fetch_job_description(data.url)
        return {'text': text}
    except job_urls.JobUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/test-provider')
async def test_provider(data: ProviderInput, x_app_token: str | None = Header(default=None)):
    verify_token(x_app_token)
    try:
        async with AI_SLOTS:
            await providers.check_connection(data.provider, data.api_key.get_secret_value(), data.model,
                                             workspace_id=data.workspace_id)
        return {'message': 'Connected. You can generate a tailored resume.'}
    except providers.ProviderError as exc:
        raise HTTPException(status_code=400, detail='Connection failed. ' + str(exc)) from exc


@app.post('/api/tailor')
async def tailor_resume(data: TailorInput, x_app_token: str | None = Header(default=None)):
    verify_token(x_app_token)
    if not data.consent:
        raise HTTPException(status_code=400, detail='Confirm before sending your resume to the selected AI provider.')
    if len(data.resume) < 20 or len(data.job_description) < 50:
        raise HTTPException(status_code=400, detail='Add a resume and a job description with enough detail.')
    try:
        async with AI_SLOTS:
            result = await providers.tailor(data.provider, data.api_key.get_secret_value(), data.model,
                                            data.resume, data.job_description, workspace_id=data.workspace_id)
        return {'resume': result.resume_text(), 'sections': [section.model_dump() for section in result.sections],
                'changes': [change.model_dump() for change in result.changes],
                'alignment': [item.model_dump() for item in result.alignment],
                'suggestions': [suggestion.model_dump() for suggestion in result.suggestions], 'warnings': result.warnings}
    except providers.ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/export')
async def export_resume(data: ExportInput, x_app_token: str | None = Header(default=None)):
    verify_token(x_app_token)
    if not data.confirmed:
        raise HTTPException(status_code=400, detail='Review and confirm the resume before downloading.')
    try:
        content = await asyncio.to_thread(exports.render_pdf if data.format == 'pdf' else exports.render_docx, data.text)
    except exports.ExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    mime = 'application/pdf' if data.format == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return Response(content, media_type=mime,
                    headers={'Content-Disposition': f'attachment; filename="tailored-resume.{data.format}"'})
