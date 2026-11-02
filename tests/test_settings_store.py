import json
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from resume_tailor import server, settings_store


SETTINGS = {'provider':'openai', 'model':'gpt-6.1-terra', 'api_key':'dummy-key-never-real', 'workspace_id':''}
HEADERS = {'X-App-Token':server.TOKEN}
RESUME = 'Avery Example\nEngineer at ExampleCo, 2020 to 2024\nBuilt reliable Java services.'
JOB = 'Backend engineer needed to build Java services. Python is a preferred skill.'


def test_saved_key_stays_on_disk_and_is_never_returned_to_browser(tmp_path, monkeypatch):
    path = tmp_path / 'config' / 'connection.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', path)
    proof = server.make_verification(SETTINGS['provider'], SETTINGS['api_key'], SETTINGS['model'], '')
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/settings').status_code == 403
        assert client.put('/api/settings', headers=HEADERS, json=SETTINGS | {'verification':'invalid'}).status_code == 400
        assert not path.exists()
        assert client.put('/api/settings', headers=HEADERS, json=SETTINGS | {'verification':proof}).status_code == 200
        response = client.get('/api/settings', headers=HEADERS)
        assert response.json() == {'saved':True, 'settings':{'provider':'openai', 'model':'gpt-6.1-terra', 'workspace_id':''}, 'legacy':False}
        assert 'dummy-key-never-real' not in response.text
        assert json.loads(path.read_text())['api_key'] == SETTINGS['api_key']
        assert 'dummy-key-never-real' not in repr(settings_store.load_settings())
        if os.name != 'nt':
            assert path.stat().st_mode & 0o777 == 0o600
        assert client.delete('/api/settings').status_code == 403
        assert client.delete('/api/settings', headers=HEADERS).status_code == 200
        assert client.get('/api/settings', headers=HEADERS).json() == {'saved':False, 'legacy':False}
    assert not path.exists()


def test_saved_key_requires_a_successful_test_and_old_proofs_stop_working(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', tmp_path / 'connection.json')
    settings_store.save_settings(settings_store.SavedSettings.model_validate(SETTINGS))
    calls = []
    async def fake_check(provider, key, model, **kwargs):
        calls.append(('check', key))
    async def fake_tailor(provider, key, model, resume, job, **kwargs):
        calls.append(('tailor', key))
        from resume_tailor.proposals import validate_proposal
        return validate_proposal({'sections':[{'heading':'Experience','lines':[{'text':'Built reliable Java services.', 'evidence':['Built reliable Java services.']}]}],
                                  'changes':[], 'alignment':[], 'suggestions':[]}, resume, job)
    monkeypatch.setattr(server.providers, 'check_connection', fake_check)
    monkeypatch.setattr(server.providers, 'tailor', fake_tailor)
    selection = {'provider':'openai', 'model':'gpt-6.1-terra', 'workspace_id':'', 'use_saved':True}
    form = selection | {'resume':RESUME, 'job_description':JOB, 'consent':True}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/tailor', headers=HEADERS, json=form).status_code == 400
        result = client.post('/api/test-provider', headers=HEADERS, json=selection)
        assert result.status_code == 200 and SETTINGS['api_key'] not in result.text
        proof = result.json()['verification']
        assert client.post('/api/tailor', headers=HEADERS, json=form | {'verification':proof}).status_code == 200
        settings_store.save_settings(settings_store.SavedSettings.model_validate(SETTINGS | {'api_key':'different-dummy-key'}))
        assert client.post('/api/tailor', headers=HEADERS, json=form | {'verification':proof}).status_code == 400
        assert client.post('/api/test-provider', headers=HEADERS, json=selection | {'provider':'gemini'}).status_code == 400
    assert calls == [('check', SETTINGS['api_key']), ('tailor', SETTINGS['api_key'])]


@pytest.mark.parametrize('field,value', [('provider','unknown'), ('api_key','short'), ('model','bad model'),
                                         ('workspace_id','not-allowed-for-openai')])
def test_rejects_invalid_saved_settings(field, value):
    with pytest.raises(ValidationError):
        settings_store.SavedSettings.model_validate(SETTINGS | {field:value})


def test_failed_replacement_preserves_the_existing_settings(tmp_path, monkeypatch):
    path = tmp_path / 'connection.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', path)
    settings_store.save_settings(settings_store.SavedSettings.model_validate(SETTINGS))
    original = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('example failure')
    monkeypatch.setattr(settings_store.os, 'replace', fail)
    with pytest.raises(settings_store.SettingsStoreError):
        settings_store.save_settings(settings_store.SavedSettings.model_validate(SETTINGS))
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_legacy_encrypted_file_is_preserved_and_corrupt_settings_can_be_forgotten(tmp_path, monkeypatch):
    path = tmp_path / 'connection.json'
    legacy = tmp_path / 'settings.json'
    legacy.write_text('previous encrypted settings')
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', path)
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/settings', headers=HEADERS).json() == {'saved':False, 'legacy':True}
        path.write_text('not a settings file')
        assert client.get('/api/settings', headers=HEADERS).json() == {'saved':True, 'corrupt':True, 'legacy':True}
        assert client.delete('/api/settings', headers=HEADERS).status_code == 200
        assert client.get('/api/settings', headers=HEADERS).json() == {'saved':False, 'legacy':True}
    assert legacy.read_text() == 'previous encrypted settings'
