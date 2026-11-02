import json
import logging
import socket

import httpx
import pytest

from resume_tailor import providers


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


@pytest.mark.parametrize('provider,host,key_header', [
    ('openai', 'api.openai.com', 'authorization'),
    ('gemini', 'generativelanguage.googleapis.com', 'x-goog-api-key'),
    ('claude', 'api.anthropic.com', 'authorization'),
])
async def test_each_provider_uses_fixed_endpoint_and_validates_proposal(monkeypatch, provider, host, key_header):
    def forbid_network(*args, **kwargs): raise AssertionError('No real network requests in this test')
    monkeypatch.setattr(socket.socket, 'connect', forbid_network)
    seen = []
    def handler(request):
        seen.append(request)
        content = json.dumps(PROPOSAL)
        if provider == 'openai':
            return httpx.Response(200, json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':content}]}]})
        if provider == 'gemini':
            return httpx.Response(200, json={'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':content}]}]})
        return httpx.Response(200, json={'stop_reason':'end_turn','content':[{'type':'text','text':content}]})
    result = await providers.tailor(provider, 'dummy-key-never-real', '', RESUME, JOB, transport=httpx.MockTransport(handler))
    assert 'dependable Java' in result.resume_text() and result.suggestions[0].skill == 'Python'
    request = seen[0]
    assert request.url.host == host and 'dummy-key-never-real' not in str(request.url)
    assert 'dummy-key-never-real' in request.headers[key_header]
    body = json.loads(request.content)
    assert 'dummy-key-never-real' not in json.dumps(body)
    if provider in ('openai', 'gemini'):
        assert body['store'] is False


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500])
async def test_provider_errors_never_expose_key_or_raw_response(status):
    key = 'dummy-secret-never-real'
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=key))
    with pytest.raises(providers.ProviderError) as raised:
        await providers.tailor('gemini', key, '', RESUME, JOB, transport=transport)
    assert key not in str(raised.value)


async def test_unverified_or_malformed_model_output_is_rejected():
    bad = {'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'{"sections": []}'}]}]}
    with pytest.raises(providers.ProviderError):
        await providers.tailor('gemini', 'dummy-key-never-real', '', RESUME, JOB,
                               transport=httpx.MockTransport(lambda request: httpx.Response(200, json=bad)))


async def test_connection_check_uses_no_resume_and_validates_result():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}]})
    await providers.check_connection('openai', 'dummy-key-never-real', '', transport=httpx.MockTransport(handler))
    assert RESUME not in seen[0].content.decode() and JOB not in seen[0].content.decode()
    assert 'ok set to true' in seen[0].content.decode()


async def test_claude_workspace_is_sent_only_to_claude():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'stop_reason':'end_turn','content':[{'type':'text','text':'{"ok":true}'}]})
    await providers.check_connection('claude', 'dummy-key-never-real', '', workspace_id='wrkspc_example',
                                     transport=httpx.MockTransport(handler))
    assert seen[0].headers['anthropic-workspace-id'] == 'wrkspc_example'
    with pytest.raises(providers.ProviderError):
        await providers.check_connection('openai', 'dummy-key-never-real', '', workspace_id='wrkspc_example',
                                         transport=httpx.MockTransport(handler))


async def test_sensitive_provider_content_is_not_logged(caplog):
    caplog.set_level(logging.DEBUG)
    key = 'dummy-secret-never-real'
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text=key + RESUME))
    with pytest.raises(providers.ProviderError):
        await providers.tailor('openai', key, '', RESUME, JOB, transport=transport)
    assert key not in caplog.text and RESUME not in caplog.text


async def test_oversized_or_timed_out_provider_responses_fail_safely():
    too_large = httpx.MockTransport(lambda request: httpx.Response(200, content=b'x' * 2_000_001))
    with pytest.raises(providers.ProviderError, match='too large'):
        await providers.tailor('openai', 'dummy-key-never-real', '', RESUME, JOB, transport=too_large)
    def timeout(request):
        raise httpx.ReadTimeout('dummy-secret-never-real', request=request)
    with pytest.raises(providers.ProviderError) as raised:
        await providers.tailor('openai', 'dummy-secret-never-real', '', RESUME, JOB, transport=httpx.MockTransport(timeout))
    assert 'dummy-secret-never-real' not in str(raised.value)
