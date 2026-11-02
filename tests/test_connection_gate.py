from fastapi.testclient import TestClient

from resume_tailor import server
from resume_tailor.proposals import validate_proposal


RESUME = 'Avery Example\navery@example.com\nEngineer at ExampleCo, 2020 to 2024\nBuilt reliable Java services.'
JOB = 'Backend engineer needed to build Java services. Python is a preferred skill.'
PROPOSAL = {
    'sections': [{'heading':'Contact','lines':[{'text':'Avery Example','evidence':['Avery Example']},
                                                {'text':'avery@example.com','evidence':['avery@example.com']}]},
                 {'heading':'Experience','lines':[{'text':'Built dependable Java services.','evidence':['Built reliable Java services.']}]}],
    'changes': [], 'alignment': [], 'suggestions': [],
}


def test_tailoring_requires_a_successful_test_of_the_exact_settings(monkeypatch):
    calls = []
    async def fake_check(provider, key, model, **kwargs): calls.append('checked')
    async def fake_tailor(provider, key, model, resume, job, **kwargs):
        calls.append('tailored')
        return validate_proposal(PROPOSAL, resume, job)
    monkeypatch.setattr(server.providers, 'check_connection', fake_check)
    monkeypatch.setattr(server.providers, 'tailor', fake_tailor)
    settings = {'provider':'openai','api_key':'dummy-key-never-real','model':'gpt-6.1-terra','workspace_id':''}
    form = settings | {'resume':RESUME,'job_description':JOB,'consent':True}
    headers = {'X-App-Token':server.TOKEN}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/tailor', headers=headers, json=form).status_code == 400
        assert not calls
        test = client.post('/api/test-provider', headers=headers, json=settings)
        assert test.status_code == 200
        proof = test.json()['verification']
        assert 'dummy-key-never-real' not in proof
        for changed in ({'api_key':'other-dummy-key-only'}, {'model':'gpt-6-luna'}, {'verification':'invalid'}):
            response = client.post('/api/tailor', headers=headers, json=form | {'verification':proof} | changed)
            assert response.status_code == 400
        assert calls == ['checked']
        result = client.post('/api/tailor', headers=headers, json=form | {'verification':proof})
        assert result.status_code == 200
        assert 'dummy-key-never-real' not in result.text
    assert calls == ['checked', 'tailored']


def test_failed_connection_does_not_return_a_verification(monkeypatch):
    async def failed_check(*args, **kwargs):
        raise server.providers.ProviderError('Check the key and account.')
    monkeypatch.setattr(server.providers, 'check_connection', failed_check)
    settings = {'provider':'openai','api_key':'dummy-key-never-real','model':'gpt-6.1-terra','workspace_id':''}
    with TestClient(server.app, base_url='http://127.0.0.1') as client:
        response = client.post('/api/test-provider', headers={'X-App-Token':server.TOKEN}, json=settings)
        assert response.status_code == 400
        assert 'verification' not in response.json() and 'dummy-key-never-real' not in response.text
