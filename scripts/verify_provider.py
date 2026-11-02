"""Check Gemini or Claude with a synthetic request and an unsaved key."""

import argparse
import getpass
import json
import logging
import os
import re
import sys
import warnings

import httpx

PROVIDERS = {
    'gemini': {'label': 'Gemini', 'key_env': 'GEMINI_API_KEY', 'model_env': 'GEMINI_MODEL',
               'model': 'gemini-3.8-flash', 'url': 'https://generativelanguage.googleapis.com/v1beta/interactions'},
    'claude': {'label': 'Claude', 'key_env': 'ANTHROPIC_API_KEY', 'model_env': 'ANTHROPIC_MODEL',
               'model': 'claude-sonnet-5-5', 'url': 'https://api.anthropic.com/v1/messages'},
}
SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
          'required': ['ok'], 'additionalProperties': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Test one provider without sending a resume.')
    parser.add_argument('provider', choices=PROVIDERS)
    provider = parser.parse_args(argv).provider
    config = PROVIDERS[provider]
    model = os.environ.get(config['model_env'], config['model']).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', model):
        print(f"Enter a valid model in {config['model_env']}, or leave it unset.")
        return 2
    workspace_id = os.environ.get('ANTHROPIC_WORKSPACE_ID', '').strip() if provider == 'claude' else ''
    if workspace_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', workspace_id):
        print('Enter a valid ANTHROPIC_WORKSPACE_ID, or leave it unset.')
        return 2
    print(f"This sends a small synthetic request to {config['label']}. No resume is sent; API charges may apply.")
    key = os.environ.get(config['key_env'], '').strip()
    if not key:
        if not sys.stdin.isatty():
            print(f"Set {config['key_env']} privately, or use an interactive terminal.")
            return 2
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                key = getpass.getpass(f"{config['label']} API key (input is hidden): ").strip()
        except (getpass.GetPassWarning, OSError):
            print('Could not hide key input. Use a terminal with hidden input.')
            return 2
        except (EOFError, KeyboardInterrupt):
            print('\nConnection check cancelled.')
            return 2
    if not key:
        print('No API key was entered.')
        return 2
    for name in ('httpx', 'httpcore'):
        logging.getLogger(name).disabled = True
    if provider == 'gemini':
        headers = {'x-goog-api-key': key}
        payload = {'model': model, 'input': 'Return an object with ok set to true.', 'store': False,
                   'generation_config': {'thinking_level': 'low', 'max_output_tokens': 2048},
                   'response_format': {'type': 'text', 'mime_type': 'application/json', 'schema': SCHEMA}}
    else:
        headers = {'Authorization': f'Bearer {key}', 'anthropic-version': '2026-10-21'}
        if workspace_id:
            headers['anthropic-workspace-id'] = workspace_id
        payload = {'model': model, 'max_tokens': 1024, 'messages': [{'role': 'user', 'content': 'Return an object with ok set to true.'}],
                   'output_config': {'format': {'type': 'json_schema', 'schema': SCHEMA}}}
    try:
        with httpx.Client(timeout=45, trust_env=False, follow_redirects=False) as client:
            response = client.post(config['url'], headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        if provider == 'gemini':
            if data.get('status') != 'completed':
                raise ValueError('Incomplete response')
            texts = [part['text'] for step in data.get('steps', []) if step.get('type') == 'model_output'
                     for part in step.get('content', []) if part.get('type') == 'text' and 'text' in part]
        else:
            if data.get('stop_reason') != 'end_turn':
                raise ValueError('Incomplete response')
            texts = [part['text'] for part in data.get('content', []) if part.get('type') == 'text' and 'text' in part]
        result = json.loads(texts[0]) if len(texts) == 1 else None
        if not isinstance(result, dict) or set(result) != {'ok'} or result['ok'] is not True:
            raise ValueError('Unexpected response')
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            message = 'Connection failed. Check your API key and model access.'
        elif status == 404:
            message = 'Connection failed. The selected model is unavailable.'
        elif status == 429:
            message = 'Connection failed. Check billing, quota, or rate limits.'
        else:
            message = 'Connection failed. Check your key, model, and account.'
        print(message)
        return 1
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError, IndexError):
        print('Connection failed. Check your internet, model access, and provider response.')
        return 1
    print(f"Connected. {config['label']} returned the expected structured response.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
