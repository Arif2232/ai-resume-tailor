import httpx
import logging
import pytest

from resume_tailor import job_urls


@pytest.mark.parametrize('url', [
    'file:///etc/passwd', 'http://127.0.0.1/', 'http://[::1]/',
    'https://user:pass@example.com/job', 'https://example.com:8443/job',
    'https://localhost/job', 'https://example.com\\@evil.example/job',
])
async def test_rejects_unsafe_urls_before_contacting_any_host(url):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail('Unexpected request'))) as client:
        with pytest.raises(job_urls.JobUrlError):
            await job_urls.fetch_job_description(url, client=client)


async def test_pins_public_address_and_preserves_host_and_tls_name(monkeypatch):
    async def resolve(host, port): return ['93.184.216.34']
    monkeypatch.setattr(job_urls, 'resolve_host', resolve)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={'content-type': 'text/html'},
                              text='<html><nav>Navigation</nav><main><h1>Software Engineer</h1><p>Build reliable services with a collaborative engineering team.</p></main></html>')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text = await job_urls.fetch_job_description('https://jobs.example.com/role?view=1', client=client)
    assert 'Software Engineer' in text and 'Build reliable services' in text and 'Navigation' not in text
    assert len(requests) == 1 and requests[0].url.host == '93.184.216.34'
    assert requests[0].headers['host'] == 'jobs.example.com'
    assert requests[0].extensions['sni_hostname'] == 'jobs.example.com'
    assert 'authorization' not in requests[0].headers


async def test_rejects_mixed_public_private_dns_answers(monkeypatch):
    async def resolve(host, port): return ['93.184.216.34', '10.0.0.7']
    monkeypatch.setattr(job_urls, 'resolve_host', resolve)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail('Unexpected request'))) as client:
        with pytest.raises(job_urls.JobUrlError):
            await job_urls.fetch_job_description('https://jobs.example.com/role', client=client)


@pytest.mark.parametrize('address', ['::ffff:127.0.0.1', '64:ff9b::a00:1', '2002:a00:1::', '169.254.169.254'])
def test_private_or_transition_addresses_are_not_public(address):
    assert not job_urls.public_address(address)


async def test_redirect_is_revalidated_before_a_second_request(monkeypatch):
    async def resolve(host, port): return ['93.184.216.34']
    monkeypatch.setattr(job_urls, 'resolve_host', resolve)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/admin'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(job_urls.JobUrlError):
            await job_urls.fetch_job_description('https://jobs.example.com/role', client=client)
    assert len(requests) == 1


async def test_extracts_structured_job_posting_from_a_page_shell(monkeypatch):
    async def resolve(host, port): return ['93.184.216.34']
    monkeypatch.setattr(job_urls, 'resolve_host', resolve)
    html = '''<html><head><script type="application/ld+json">{"@context":"https://schema.org",
      "@type":"JobPosting","title":"Backend Engineer",
      "description":"<p>Build dependable services with Python and collaborate with product teams.</p>"}</script></head>
      <body><div>Loading...</div></body></html>'''
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={'content-type':'text/html'}, text=html))) as client:
        text = await job_urls.fetch_job_description('https://jobs.example.com/role', client=client)
    assert 'Backend Engineer' in text and 'Build dependable services' in text


async def test_job_url_query_is_not_logged(monkeypatch, caplog):
    async def resolve(host, port): return ['93.184.216.34']
    monkeypatch.setattr(job_urls, 'resolve_host', resolve)
    caplog.set_level(logging.DEBUG)
    html = '<main>Backend engineer needed to build dependable services with a collaborative team.</main>'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={'content-type':'text/html'}, text=html))) as client:
        await job_urls.fetch_job_description('https://jobs.example.com/role?private_token=dummy-secret', client=client)
    assert 'dummy-secret' not in caplog.text


async def test_cross_host_redirect_uses_a_fresh_tls_connection(monkeypatch):
    async def resolve(host, port): return ['93.184.216.34']
    monkeypatch.setattr(job_urls, 'resolve_host', resolve)
    requests, clients = [], []
    def handler(request):
        requests.append(request)
        if request.headers['host'] == 'first.example':
            return httpx.Response(302, headers={'location':'https://second.example/job'})
        return httpx.Response(200, headers={'content-type':'text/html'},
                              text='<main>Backend engineer needed to build dependable services with a collaborative team.</main>')
    real_client = httpx.AsyncClient
    def make_client(**kwargs):
        clients.append(True)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(job_urls.httpx, 'AsyncClient', make_client)
    assert 'Backend engineer' in await job_urls.fetch_job_description('https://first.example/job')
    assert len(clients) == 2
    assert [request.extensions['sni_hostname'] for request in requests] == ['first.example', 'second.example']


@pytest.mark.parametrize('headers,body', [
    ({'content-type': 'application/pdf'}, b'not html'),
    ({'content-type': 'text/html', 'content-encoding': 'gzip'}, b'compressed'),
    ({'content-type': 'text/html', 'content-length': '2000000'}, b'large'),
])
async def test_rejects_unsupported_or_oversized_responses(monkeypatch, headers, body):
    async def resolve(host, port): return ['93.184.216.34']
    monkeypatch.setattr(job_urls, 'resolve_host', resolve)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, headers=headers, content=body))) as client:
        with pytest.raises(job_urls.JobUrlError):
            await job_urls.fetch_job_description('https://jobs.example.com/role', client=client)
