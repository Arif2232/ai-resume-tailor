import json
import socket

import httpx
import pytest

from scripts import verify_provider


@pytest.mark.parametrize('provider,env,host,key_header', [
    ('gemini', 'GEMINI_API_KEY', 'generativelanguage.googleapis.com', 'x-goog-api-key'),
    ('claude', 'ANTHROPIC_API_KEY', 'api.anthropic.com', 'authorization'),
])
def test_provider_check_uses_synthetic_data_and_official_endpoint(monkeypatch, capsys, provider, env, host, key_header):
    key = 'dummy-secret-never-real'
    seen = []
    def forbid_network(*args, **kwargs):
        raise AssertionError('No network access in offline tests')
    def handler(request):
        seen.append(request)
        if provider == 'gemini':
            return httpx.Response(200, json={'status': 'completed', 'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': '{"ok":true}'}]}]})
        return httpx.Response(200, json={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{"ok":true}'}]})
    real_client = httpx.Client
    monkeypatch.setattr(socket.socket, 'connect', forbid_network)
    monkeypatch.setattr(verify_provider.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv(env, key)
    assert verify_provider.main([provider]) == 0
    assert len(seen) == 1 and seen[0].url.host == host
    assert key in seen[0].headers[key_header] and key not in str(seen[0].url)
    payload = json.loads(seen[0].content)
    assert key not in json.dumps(payload)
    if provider == 'gemini':
        assert payload['store'] is False
    output = capsys.readouterr()
    assert key not in output.out + output.err and 'Connected' in output.out


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500])
def test_provider_failure_is_sanitized(monkeypatch, capsys, status):
    key = 'dummy-secret-never-real'
    real_client = httpx.Client
    monkeypatch.setattr(verify_provider.httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text=key)), **kwargs))
    monkeypatch.setenv('GEMINI_API_KEY', key)
    assert verify_provider.main(['gemini']) != 0
    output = capsys.readouterr()
    assert key not in output.out + output.err
    assert 'Connect' in output.out or 'key' in output.out or 'limit' in output.out or 'model' in output.out


def test_incomplete_provider_response_never_passes(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(verify_provider.httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'status': 'incomplete', 'steps': []})), **kwargs))
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy-key-not-real')
    assert verify_provider.main(['gemini']) != 0


def test_claude_check_supports_workspace_without_sending_it_to_another_provider(monkeypatch):
    seen = []
    real_client = httpx.Client
    def handler(request):
        seen.append(request)
        if request.url.host == 'generativelanguage.googleapis.com':
            return httpx.Response(200, json={'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'{"ok":true}'}]}]})
        return httpx.Response(200, json={'stop_reason':'end_turn','content':[{'type':'text','text':'{"ok":true}'}]})
    monkeypatch.setattr(verify_provider.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'dummy-key-never-real')
    monkeypatch.setenv('ANTHROPIC_WORKSPACE_ID', 'wrkspc_example')
    assert verify_provider.main(['claude']) == 0
    assert seen[0].headers['anthropic-workspace-id'] == 'wrkspc_example'
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy-key-never-real')
    assert verify_provider.main(['gemini']) == 0
    assert 'anthropic-workspace-id' not in seen[1].headers
