import base64
import json
import os

import pytest
from fastapi.testclient import TestClient

from resume_tailor import server, settings_store


def envelope():
    encode = lambda value: base64.b64encode(value).decode('ascii')
    return {'version':1,'kdf':'PBKDF2-SHA256','iterations':600000,
            'salt':encode(b's' * 16),'iv':encode(b'i' * 12),'ciphertext':encode(b'ciphertext-only' * 3)}


def test_only_encrypted_settings_are_saved_and_removable(tmp_path, monkeypatch):
    path = tmp_path / 'config' / 'settings.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', path)
    settings = {'provider':'openai','model':'gpt-6.1-terra','api_key':'dummy-key-never-real','workspace_id':''}
    proof = server.make_verification('openai', settings['api_key'], settings['model'], '')
    headers = {'X-App-Token':server.TOKEN}
    data = settings | {'verification':proof, 'encrypted':envelope()}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/settings').status_code == 403
        assert client.put('/api/settings', headers=headers, json=data | {'verification':'invalid'}).status_code == 400
        assert not path.exists()
        assert client.put('/api/settings', headers=headers, json=data).status_code == 200
        saved = client.get('/api/settings', headers=headers).json()
        assert saved == {'saved':True,'encrypted':envelope()}
        assert 'dummy-key-never-real' not in path.read_text() and 'dummy-key-never-real' not in json.dumps(saved)
        if os.name != 'nt': assert path.stat().st_mode & 0o777 == 0o600
        assert client.delete('/api/settings').status_code == 403
        assert client.delete('/api/settings', headers=headers).status_code == 200
        assert client.get('/api/settings', headers=headers).json() == {'saved':False}
    assert not path.exists()


@pytest.mark.parametrize('field,value', [('salt','bad'), ('iv','bad'), ('ciphertext','bad'), ('iterations',1),
                                         ('version',2), ('version',True), ('version',1.0)])
def test_rejects_invalid_encrypted_envelope_without_writing(tmp_path, monkeypatch, field, value):
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', path)
    settings = {'provider':'openai','model':'gpt-6.1-terra','api_key':'dummy-key-never-real','workspace_id':''}
    proof = server.make_verification('openai', settings['api_key'], settings['model'], '')
    bad = envelope() | {field:value}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        response = client.put('/api/settings', headers={'X-App-Token':server.TOKEN},
                              json=settings | {'verification':proof,'encrypted':bad})
    assert response.status_code == 400 and not path.exists()


def test_failed_replacement_preserves_the_existing_vault(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', path)
    settings_store.save_settings(settings_store.EncryptedSettings.model_validate(envelope()))
    original = path.read_bytes()
    def fail(*args, **kwargs): raise OSError('example failure')
    monkeypatch.setattr(settings_store.os, 'replace', fail)
    with pytest.raises(settings_store.SettingsStoreError):
        settings_store.save_settings(settings_store.EncryptedSettings.model_validate(envelope()))
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_corrupt_settings_can_be_forgotten(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    path.write_text('not a settings file')
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', path)
    headers = {'X-App-Token':server.TOKEN}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/settings', headers=headers).json() == {'saved':True, 'corrupt':True}
        assert client.delete('/api/settings', headers=headers).status_code == 200
        assert client.get('/api/settings', headers=headers).json() == {'saved':False}
