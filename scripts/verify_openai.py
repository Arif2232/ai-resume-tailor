"""Check an OpenAI key and model with synthetic text; never save the key."""

import getpass
import json
import logging
import os
import re
import sys
import warnings

try:
    import httpx
    import openai
except ImportError:
    httpx = openai = None


def main() -> int:
    if httpx is None or openai is None:
        print('Install the project dependencies before running this check.')
        return 2

    if os.environ.get('OPENAI_CUSTOM_HEADERS', '').strip():
        print('Unset OPENAI_CUSTOM_HEADERS in this terminal before running this check.')
        return 2

    model = os.environ.get('OPENAI_MODEL', 'gpt-6.1-terra').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', model):
        print('Enter a valid model name in OPENAI_MODEL, or leave it unset.')
        return 2

    print('This sends a small synthetic request to OpenAI. No resume is sent; API charges may apply.')
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        if not sys.stdin.isatty():
            print('Set OPENAI_API_KEY for this terminal, or run the check in an interactive terminal.')
            return 2
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                key = getpass.getpass('OpenAI API key (input is hidden): ').strip()
        except (getpass.GetPassWarning, OSError):
            print('Could not hide key input. Use a terminal with hidden input or set OPENAI_API_KEY privately.')
            return 2
        except (EOFError, KeyboardInterrupt):
            print('\nConnection check cancelled.')
            return 2
    if not key:
        print('No API key was entered.')
        return 2

    for logger in ('openai', 'httpx', 'httpcore'):
        logging.getLogger(logger).disabled = True

    request = {
        'model': model,
        'input': 'Return an object with ok set to true.',
        'max_output_tokens': 128,
        'store': False,
        'text': {'format': {
            'type': 'json_schema', 'name': 'connection_check', 'strict': True,
            'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                       'required': ['ok'], 'additionalProperties': False},
        }},
    }
    if model in {'gpt-6.1-terra', 'gpt-6-luna'}:
        request['reasoning'] = {'effort': 'none'}

    try:
        with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as transport, openai.OpenAI(
            api_key=key, base_url='https://api.openai.com/v1', timeout=30, max_retries=0, http_client=transport,
        ) as client:
            response = client.responses.create(**request)
        result = json.loads(response.output_text)
    except Exception as exc:
        status = getattr(exc, 'status_code', None)
        if isinstance(exc, openai.APITimeoutError):
            message = 'The request timed out. Check your connection and try again.'
        elif isinstance(exc, openai.APIConnectionError):
            message = 'Could not connect to OpenAI. Check your internet connection.'
        elif status == 401:
            message = 'OpenAI rejected the API key. Check the key and try again.'
        elif status == 403:
            message = 'This key does not have permission to use the selected model.'
        elif status == 404:
            message = 'The selected model is unavailable. Check the model name and access.'
        elif status == 429:
            message = 'OpenAI reported a usage limit. Check API billing, credits, or rate limits.'
        elif status == 400:
            message = 'OpenAI rejected the test request. Check the selected model.'
        elif isinstance(exc, (ValueError, TypeError)):
            message = 'OpenAI did not return a readable structured response. Try again or check model support.'
        else:
            message = 'The connection check failed. Check your model, account, and connection.'
        print(message)
        return 1

    if response.status != 'completed' or not isinstance(result, dict) or set(result) != {'ok'} or result['ok'] is not True:
        print('OpenAI did not return the expected completed response. Check model support and try again.')
        return 1
    print('Connected. OpenAI returned the expected structured response.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
