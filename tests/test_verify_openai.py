import socket
import warnings
from types import SimpleNamespace

import httpx
import openai
import pytest

from scripts import verify_openai


DUMMY_KEY = 'dummy-secret-never-real'


@pytest.fixture
def fake_provider(monkeypatch):
    """Reject network access and record only synthetic calls."""
    record = {'response': SimpleNamespace(status='completed', output_text='{"ok": true}')}

    def forbid_network(*args, **kwargs):
        raise AssertionError('The test must not access the network')

    class FakeTransport:
        def __init__(self, **kwargs):
            record['transport'] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeResponses:
        def create(self, **kwargs):
            record['request'] = kwargs
            if 'error' in record:
                raise record['error']
            return record['response']

    class FakeOpenAI:
        def __init__(self, **kwargs):
            record['client'] = kwargs
            self.responses = FakeResponses()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(socket.socket, 'connect', forbid_network)
    monkeypatch.setattr(verify_openai.httpx, 'Client', FakeTransport)
    monkeypatch.setattr(verify_openai.openai, 'OpenAI', FakeOpenAI)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    monkeypatch.delenv('OPENAI_CUSTOM_HEADERS', raising=False)
    return record


def test_no_key_and_no_terminal_does_not_send_a_request(fake_provider, monkeypatch, capsys):
    monkeypatch.setattr(verify_openai.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    assert verify_openai.main() != 0
    assert 'client' not in fake_provider
    assert 'key' in capsys.readouterr().out.lower()


def test_interactive_key_is_requested_without_printing_it(fake_provider, monkeypatch, capsys):
    monkeypatch.setattr(verify_openai.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []

    def read_hidden(prompt):
        prompts.append(prompt)
        return DUMMY_KEY

    monkeypatch.setattr(verify_openai.getpass, 'getpass', read_hidden)
    assert verify_openai.main() == 0
    output = capsys.readouterr()
    assert prompts and fake_provider['client']['api_key'] == DUMMY_KEY
    assert DUMMY_KEY not in output.out + output.err


def test_insecure_hidden_input_warning_cancels_before_any_request(fake_provider, monkeypatch, capsys):
    monkeypatch.setattr(verify_openai.sys, 'stdin', SimpleNamespace(isatty=lambda: True))

    def unsafe_prompt(*args):
        warnings.warn('Input may be echoed', verify_openai.getpass.GetPassWarning)
        return DUMMY_KEY

    monkeypatch.setattr(verify_openai.getpass, 'getpass', unsafe_prompt)
    assert verify_openai.main() != 0
    assert 'client' not in fake_provider
    output = capsys.readouterr()
    assert DUMMY_KEY not in output.out + output.err
    assert 'hide' in (output.out + output.err).lower()


def test_environment_key_is_sent_only_to_the_official_endpoint(fake_provider, monkeypatch, capsys):
    monkeypatch.setenv('OPENAI_API_KEY', DUMMY_KEY)
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://untrusted.example/v1')
    monkeypatch.setattr(verify_openai.getpass, 'getpass', lambda *args: pytest.fail('Unexpected key prompt'))
    assert verify_openai.main() == 0
    client = fake_provider['client']
    transport = fake_provider['transport']
    request = fake_provider['request']
    assert client['api_key'] == DUMMY_KEY
    assert client['base_url'] == 'https://api.openai.com/v1'
    assert client['timeout'] == 30 and client['max_retries'] == 0
    assert transport['trust_env'] is False and transport['follow_redirects'] is False
    assert request['model'] == 'gpt-6.1-terra' and request['store'] is False
    assert request['max_output_tokens'] <= 512
    schema = request['text']['format']
    assert schema['type'] == 'json_schema' and schema['strict'] is True
    assert schema['schema']['properties']['ok']['type'] == 'boolean'
    assert 'ok' in schema['schema']['required']
    assert DUMMY_KEY not in str(request)
    output = capsys.readouterr()
    assert DUMMY_KEY not in output.out + output.err
    assert 'resume' in output.out.lower() and ('charge' in output.out.lower() or 'cost' in output.out.lower())


def test_model_can_be_selected_without_sending_resume_data(fake_provider, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', DUMMY_KEY)
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-6-luna')
    assert verify_openai.main() == 0
    request = fake_provider['request']
    assert request['model'] == 'gpt-6-luna'
    assert DUMMY_KEY not in str(request['input'])


@pytest.mark.parametrize('status,body', [
    ('incomplete', '{"ok": true}'),
    ('completed', ''),
    ('completed', 'not-json'),
    ('completed', '{"ok": false}'),
    ('completed', '{"ok": 1}'),
    ('completed', '{"ok": true, "extra": 1}'),
])
def test_incomplete_or_invalid_responses_do_not_report_success(fake_provider, monkeypatch, status, body, capsys):
    monkeypatch.setenv('OPENAI_API_KEY', DUMMY_KEY)
    fake_provider['response'] = SimpleNamespace(status=status, output_text=body)
    assert verify_openai.main() != 0
    output = capsys.readouterr()
    assert DUMMY_KEY not in output.out + output.err


@pytest.mark.parametrize('status,words', [
    (401, ('key',)),
    (403, ('access', 'permission')),
    (404, ('model',)),
    (429, ('billing', 'quota', 'rate', 'limit')),
])
def test_provider_errors_are_actionable_without_printing_secrets(fake_provider, monkeypatch, status, words, capsys):
    class ProviderError(Exception):
        status_code = status

    monkeypatch.setenv('OPENAI_API_KEY', DUMMY_KEY)
    fake_provider['error'] = ProviderError(DUMMY_KEY)
    assert verify_openai.main() != 0
    output = capsys.readouterr()
    assert DUMMY_KEY not in output.out + output.err
    assert any(word in (output.out + output.err).lower() for word in words)


def test_timeout_is_reported_without_request_details(fake_provider, monkeypatch, capsys):
    monkeypatch.setenv('OPENAI_API_KEY', DUMMY_KEY)
    request = httpx.Request('POST', 'https://api.openai.com/v1/responses', headers={'Authorization': f'Bearer {DUMMY_KEY}'})
    fake_provider['error'] = openai.APITimeoutError(request=request)
    assert verify_openai.main() != 0
    output = capsys.readouterr()
    assert DUMMY_KEY not in output.out + output.err
    assert 'tim' in (output.out + output.err).lower()


@pytest.mark.parametrize('custom_header', [
    None, 'Authorization: Bearer alternate-dummy-key', 'authorization: Bearer alternate-dummy-key',
    'AUTHORIZATION: Bearer alternate-dummy-key', 'Host: untrusted.example', 'host: untrusted.example',
])
def test_official_sdk_serializes_the_synthetic_request_with_mock_transport(monkeypatch, capsys, custom_header):
    import json

    seen = []

    def forbid_network(*args, **kwargs):
        raise AssertionError('The test must not access the network')

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={
            'id': 'resp_example', 'object': 'response', 'created_at': 0, 'status': 'completed',
            'model': 'gpt-6.1-terra', 'output': [{
                'id': 'msg_example', 'type': 'message', 'status': 'completed', 'role': 'assistant',
                'content': [{'type': 'output_text', 'text': '{"ok":true}', 'annotations': []}],
            }],
        })

    def client_factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setenv('OPENAI_API_KEY', DUMMY_KEY)
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://untrusted.example/v1')
    if custom_header:
        monkeypatch.setenv('OPENAI_CUSTOM_HEADERS', custom_header)
    else:
        monkeypatch.delenv('OPENAI_CUSTOM_HEADERS', raising=False)
    monkeypatch.setattr(verify_openai, 'httpx', SimpleNamespace(Client=client_factory))
    monkeypatch.setattr(socket.socket, 'connect', forbid_network)
    result = verify_openai.main()
    if result != 0:
        output = capsys.readouterr()
        assert custom_header and not seen
        assert 'header' in (output.out + output.err).lower()
        assert DUMMY_KEY not in output.out + output.err and 'alternate-dummy-key' not in output.out + output.err
        return
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == 'https://api.openai.com/v1/responses'
    assert request.headers['host'] == 'api.openai.com'
    assert request.headers['authorization'] == f'Bearer {DUMMY_KEY}'
    payload = json.loads(request.content)
    assert payload['store'] is False
    assert payload['text']['format']['schema']['required'] == ['ok']
    assert DUMMY_KEY not in request.content.decode()
    output = capsys.readouterr()
    assert DUMMY_KEY not in output.out + output.err
