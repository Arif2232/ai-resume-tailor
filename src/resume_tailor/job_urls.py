"""Fetch public job pages without allowing access to local networks."""

import asyncio
import ipaddress
import json
import re
import socket
from contextlib import nullcontext
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from resume_tailor.privacy import silence_http_logs

MAX_RESPONSE_BYTES = 1_000_000
MAX_JOB_CHARS = 30_000
MAX_REDIRECTS = 3


class JobUrlError(ValueError):
    pass


async def resolve_host(host: str, port: int) -> list[str]:
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=5,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise JobUrlError('Could not find the job website. Paste the description instead.') from exc
    return list(dict.fromkeys(item[4][0] for item in addresses))


def public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped.is_global
        if any(address in ipaddress.ip_network(network) for network in
               ('64:ff9b::/96', '64:ff9b:1::/48', '2002::/16', '2001::/32')):
            return False
    return True


async def pinned_url(value: str):
    if not value or len(value) > 4096 or '\\' in value or any(ord(char) < 32 for char in value):
        raise JobUrlError('Enter a valid public job URL.')
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname or '@' in parsed.netloc:
            raise ValueError('Invalid URL')
        scheme = parsed.scheme.lower()
        port = parsed.port or (443 if scheme == 'https' else 80)
        if port != (443 if scheme == 'https' else 80):
            raise ValueError('Unsupported port')
        host = parsed.hostname.rstrip('.').encode('idna').decode('ascii').lower()
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
            if host == 'localhost' or not re.fullmatch(r'[a-z0-9.-]+', host) or '..' in host:
                raise ValueError('Invalid hostname')
    except (ValueError, UnicodeError) as exc:
        raise JobUrlError('Enter a valid public job URL without credentials or a custom port.') from exc
    addresses = [str(literal)] if literal is not None else await resolve_host(host, port)
    if not addresses or not all(public_address(address) for address in addresses):
        raise JobUrlError('This URL does not point to a public website. Paste the description instead.')
    address = ipaddress.ip_address(addresses[0])
    netloc = f'[{address.compressed}]' if address.version == 6 else address.compressed
    target = urlunsplit((scheme, netloc, parsed.path or '/', parsed.query, ''))
    host_header = f'[{host}]' if literal is not None and literal.version == 6 else host
    return target, host_header, host


def extract_text(content: bytes, content_type: str) -> str:
    if content_type == 'text/plain':
        text = content.decode('utf-8', errors='replace')
    else:
        soup = BeautifulSoup(content, 'html.parser')
        postings = []
        def find_postings(node, depth=0):
            if depth > 8:
                return
            if isinstance(node, list):
                for item in node[:500]:
                    find_postings(item, depth + 1)
            elif isinstance(node, dict):
                types = node.get('@type', [])
                if (types == 'JobPosting' or isinstance(types, list) and 'JobPosting' in types) and isinstance(node.get('description'), str):
                    postings.append(node)
                if '@graph' in node:
                    find_postings(node['@graph'], depth + 1)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                find_postings(json.loads(script.string or script.get_text()))
            except (ValueError, TypeError, RecursionError):
                continue
        for element in soup(['script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        if len(postings) == 1:
            posting = postings[0]
            description = BeautifulSoup(posting['description'], 'html.parser')
            for element in description(['script', 'style', 'noscript']):
                element.decompose()
            title = posting.get('title') if isinstance(posting.get('title'), str) else ''
            text = title + '\n' + description.get_text('\n', strip=True)
        else:
            main = soup.find('main') or soup.find('article') or soup.body or soup
            text = main.get_text('\n', strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = '\n'.join(lines)
    if len(text) < 50:
        raise JobUrlError('Could not find a readable job description. Paste it instead.')
    if len(text) > MAX_JOB_CHARS:
        raise JobUrlError('The job description is too long. Paste the relevant sections instead.')
    return text


async def fetch_job_description(url: str, *, client: httpx.AsyncClient | None = None) -> str:
    silence_http_logs()
    current = url
    try:
        for count in range(MAX_REDIRECTS + 1):
            target, host_header, host = await pinned_url(current)
            # A fresh pool prevents reusing a TLS connection for another hostname on the same IP.
            context = nullcontext(client) if client is not None else httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False)
            async with context as active:
                async with active.stream('GET', target, headers={'Host': host_header, 'Accept-Encoding': 'identity',
                                                                  'Accept': 'text/html, text/plain'},
                                         extensions={'sni_hostname': host}, follow_redirects=False) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get('location')
                        if not location or count == MAX_REDIRECTS:
                            raise JobUrlError('The job link redirected too many times. Paste the description instead.')
                        current = urljoin(current, location)
                        continue
                    if response.status_code != 200:
                        raise JobUrlError('The job page could not be opened. Paste the description instead.')
                    content_type = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
                    if content_type not in ('text/html', 'text/plain'):
                        raise JobUrlError('This job link is not a readable web page. Paste the description instead.')
                    if response.headers.get('content-encoding', 'identity').lower() not in ('', 'identity'):
                        raise JobUrlError('The job page could not be read safely. Paste the description instead.')
                    length = response.headers.get('content-length')
                    if length and (not length.isdecimal() or int(length) > MAX_RESPONSE_BYTES):
                        raise JobUrlError('The job page is too large. Paste the description instead.')
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise JobUrlError('The job page is too large. Paste the description instead.')
                    return extract_text(bytes(content), content_type)
    except JobUrlError:
        raise
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise JobUrlError('The job page could not be opened. Paste the description instead.') from exc
    raise JobUrlError('The job page could not be opened. Paste the description instead.')
