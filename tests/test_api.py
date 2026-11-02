import io

from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from resume_tailor import server
from resume_tailor.proposals import validate_proposal


RESUME = 'Avery Example\navery@example.com\nEngineer at ExampleCo, 2020 to 2024\nBuilt reliable Java services.'
JOB = 'Backend engineer needed to build Java services. Python is a preferred skill.'
PROPOSAL = {
    'sections': [
        {'heading': 'Contact', 'lines': [{'text': 'Avery Example', 'evidence': ['Avery Example']},
                                        {'text': 'avery@example.com', 'evidence': ['avery@example.com']}]},
        {'heading': 'Experience', 'lines': [{'text': 'Engineer at ExampleCo, 2020 to 2024', 'evidence': ['Engineer at ExampleCo, 2020 to 2024']},
                                           {'text': 'Built dependable Java services.', 'evidence': ['Built reliable Java services.']}]},
    ],
    'changes': [{'before': 'Built reliable Java services.', 'after': 'Built dependable Java services.', 'reason': 'Clarifies backend work.'}],
    'alignment': [{'point':'Java work relates to the role.', 'resume_evidence':'Built reliable Java services.', 'job_evidence':'build Java services'}],
    'suggestions': [{'skill': 'Python', 'job_evidence': 'Python is a preferred skill.'}],
}


def example_pdf():
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(50, 750, 'Avery Example - Software Engineer')
    page.drawString(50, 730, 'Built reliable Java services for customers.')
    page.save()
    return output.getvalue()


def test_local_api_checks_token_and_does_not_echo_secrets(monkeypatch):
    calls = []
    async def fake_tailor(provider, key, model, resume, job, **kwargs):
        calls.append((provider, resume, job))
        return validate_proposal(PROPOSAL, resume, job)
    monkeypatch.setattr(server.providers, 'tailor', fake_tailor)
    data = {'provider':'openai','api_key':'dummy-secret-never-real','model':'gpt-6.1-terra',
            'resume':RESUME,'job_description':JOB,'consent':True}
    data['verification'] = server.make_verification('openai', data['api_key'], data['model'], '')
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/tailor', json=data).status_code == 403
        assert client.post('/api/tailor', headers={'X-App-Token':server.TOKEN}, json=data | {'consent':False}).status_code == 400
        assert not calls
        result = client.post('/api/tailor', headers={'X-App-Token':server.TOKEN}, json=data)
    assert result.status_code == 200 and result.json()['suggestions'][0]['skill'] == 'Python'
    assert 'dummy-secret-never-real' not in result.text and len(calls) == 1


def test_upload_and_reviewed_exports_work_without_storing_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    headers = {'X-App-Token':server.TOKEN, 'X-Resume-Filename':'resume.pdf', 'Content-Type':'application/pdf'}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/resume', content=example_pdf(), headers={'X-Resume-Filename':'resume.pdf'}).status_code == 403
        extracted = client.post('/api/resume', content=example_pdf(), headers=headers)
        assert extracted.status_code == 200 and 'Avery Example' in extracted.json()['text']
        assert client.post('/api/export', headers={'X-App-Token':server.TOKEN},
                           json={'text':RESUME,'format':'pdf','confirmed':False}).status_code == 400
        pdf = client.post('/api/export', headers={'X-App-Token':server.TOKEN},
                          json={'text':RESUME,'format':'pdf','confirmed':True})
        word = client.post('/api/export', headers={'X-App-Token':server.TOKEN},
                           json={'text':RESUME,'format':'docx','confirmed':True})
    assert pdf.status_code == word.status_code == 200
    assert 'Avery Example' in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    assert 'Avery Example' in '\n'.join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
    assert not list(tmp_path.rglob('*'))


def test_invalid_requests_do_not_return_user_data_or_accept_other_hosts():
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        bad = client.post('/api/tailor', headers={'X-App-Token':server.TOKEN},
                          json={'api_key':'dummy-secret-never-real','resume':RESUME})
        assert bad.status_code in (400, 422) and 'dummy-secret-never-real' not in bad.text and RESUME not in bad.text
        assert client.get('/', headers={'Host':'evil.example'}).status_code == 400


def test_job_url_and_connection_checks_use_only_requested_inputs(monkeypatch):
    seen = []
    async def fake_fetch(url):
        seen.append(('url', url))
        return JOB
    async def fake_check(provider, key, model, **kwargs):
        seen.append(('check', provider, model))
    monkeypatch.setattr(server.job_urls, 'fetch_job_description', fake_fetch)
    monkeypatch.setattr(server.providers, 'check_connection', fake_check)
    headers = {'X-App-Token':server.TOKEN}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/options').status_code == 403
        options = client.get('/api/options', headers=headers).json()
        assert set(options) == {'openai', 'gemini', 'claude'} and options['claude']['experimental']
        result = client.post('/api/job-url', headers=headers, json={'url':'https://example.com/job'})
        assert result.status_code == 200 and result.json()['text'] == JOB
        result = client.post('/api/test-provider', headers=headers,
                             json={'provider':'openai','model':'gpt-6.1-terra','api_key':'dummy-secret-never-real'})
        assert result.status_code == 200 and 'dummy-secret-never-real' not in result.text
    assert seen == [('url', 'https://example.com/job'), ('check', 'openai', 'gpt-6.1-terra')]


def test_oversized_requests_are_rejected_before_processing():
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        response = client.post('/api/resume', headers={'X-App-Token':server.TOKEN, 'X-Resume-Filename':'resume.pdf',
                                                       'Content-Length':'5000001'}, content=b'%PDF-small')
        assert response.status_code == 413
        assert response.headers['Cache-Control'] == 'no-store'


def test_unexpected_failure_does_not_expose_the_key(monkeypatch, caplog):
    async def fail(provider, key, model, resume, job, **kwargs):
        raise RuntimeError(key)
    monkeypatch.setattr(server.providers, 'tailor', fail)
    key = 'dummy-secret-never-real'
    data = {'provider':'openai','api_key':key,'model':'gpt-6.1-terra','resume':RESUME,'job_description':JOB,'consent':True}
    data['verification'] = server.make_verification('openai', key, data['model'], '')
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        response = client.post('/api/tailor', headers={'X-App-Token':server.TOKEN}, json=data)
    assert response.status_code == 500 and key not in response.text and key not in caplog.text


def test_unverified_suggestion_is_omitted_and_reported(monkeypatch):
    proposal = PROPOSAL | {'suggestions': PROPOSAL['suggestions'] + [{'skill':'Docker','job_evidence':'Docker is required.'}]}
    async def fake_tailor(provider, key, model, resume, job, **kwargs):
        return validate_proposal(proposal, resume, job)
    monkeypatch.setattr(server.providers, 'tailor', fake_tailor)
    data = {'provider':'openai','api_key':'dummy-key-never-real','model':'gpt-6.1-terra',
            'resume':RESUME,'job_description':JOB,'consent':True}
    data['verification'] = server.make_verification('openai', data['api_key'], data['model'], '')
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        response = client.post('/api/tailor', headers={'X-App-Token':server.TOKEN}, json=data)
    assert response.status_code == 200
    assert [item['skill'] for item in response.json()['suggestions']] == ['Python']
    assert response.json()['warnings']
