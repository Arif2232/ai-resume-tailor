import asyncio
import io
import json
import socket

import uvicorn
from docx import Document
from playwright.async_api import async_playwright, expect
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from resume_tailor import server as application, settings_store
from resume_tailor.server import app


def example_pdf():
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(50, 750, 'Avery Example - Software Engineer')
    page.drawString(50, 730, 'Built reliable Java services for customers.')
    page.save()
    return output.getvalue()


async def test_browser_flow_reviews_suggestions_and_exports_without_real_ai(tmp_path, monkeypatch):
    saved_file = tmp_path / 'config' / 'connection.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_PATH', saved_file)
    checks = []
    fail_next = [False]
    async def fake_check(provider, key, model, **kwargs):
        checks.append({'provider':provider, 'api_key':key, 'model':model, **kwargs})
        if len(checks) == 1 or fail_next[0]:
            fail_next[0] = False
            raise application.providers.ProviderError('Check the key.')
    monkeypatch.setattr(application.providers, 'check_connection', fake_check)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(32)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1280, 'height': 900})
            await page.goto(f'http://127.0.0.1:{port}/')
            await page.wait_for_selector('#provider option[value="gemini"]', state='attached')
            assert await page.locator('#provider').input_value() == 'openai'
            await expect(page.locator('#generate')).to_be_disabled()
            await page.locator('#resume-file').set_input_files({'name':'resume.pdf','mimeType':'application/pdf','buffer':example_pdf()})
            await expect(page.locator('#resume-status')).to_contain_text('Resume loaded')
            assert 'Avery Example' in await page.locator('#resume-text').input_value()
            await page.locator('#job-text').fill('Backend engineer needed to build Java services. Python is a preferred skill.')
            await page.locator('#open-settings').click()
            assert await page.locator('#save-password, #confirm-password, #unlock-password').count() == 0
            await page.select_option('#provider', 'gemini')
            await expect(page.locator('#provider-note')).to_contain_text('free-tier')
            await page.locator('#api-key').fill('dummy-key-never-real')
            async with page.expect_response('**/api/test-provider'):
                await page.locator('#test-provider').click()
            await expect(page.locator('#connection-status')).to_contain_text('Connection failed')
            await expect(page.locator('#save-settings')).to_be_disabled()
            async with page.expect_response('**/api/test-provider'):
                await page.locator('#test-provider').click()
            await expect(page.locator('#connection-status')).to_contain_text('Connected')
            await expect(page.locator('#save-settings')).to_be_enabled()
            assert set(checks[0]) == {'provider','model','api_key','workspace_id'} and checks[0]['provider'] == 'gemini'
            await page.locator('#api-key').fill('different-dummy-key')
            await expect(page.locator('#save-settings')).to_be_disabled()
            await page.locator('#api-key').fill('dummy-key-never-real')
            await page.locator('#test-provider').click()
            await expect(page.locator('#save-settings')).to_be_enabled()
            stale = await browser.new_page()
            async with stale.expect_response('**/api/settings'):
                await stale.goto(f'http://127.0.0.1:{port}/')
            await page.locator('#save-settings').click()
            await expect(page.locator('#settings-dialog')).not_to_be_visible()
            await expect(page.locator('#active-provider')).to_have_text('Gemini connected')
            await expect(page.locator('#generate')).to_be_enabled()
            assert json.loads(saved_file.read_text())['api_key'] == 'dummy-key-never-real'
            original_settings = saved_file.read_bytes()
            await stale.locator('#open-settings').click()
            await stale.locator('#api-key').fill('another-dummy-key-only')
            await stale.locator('#test-provider').click()
            await expect(stale.locator('#save-settings')).to_be_enabled()
            refused = asyncio.Event()
            async def refuse_replacement(dialog):
                await dialog.dismiss()
                refused.set()
            stale.once('dialog', refuse_replacement)
            await stale.locator('#save-settings').click()
            await asyncio.wait_for(refused.wait(), timeout=5)
            await expect(stale.locator('#settings-dialog')).to_be_visible()
            assert saved_file.read_bytes() == original_settings
            assert 'Avery Example' in await page.locator('#resume-text').input_value()
            await page.locator('.import-details summary').click()
            await page.locator('#job-url').fill('https://example.com/job')
            imports = []
            async def fake_import(route):
                imports.append(json.loads(route.request.post_data))
                await route.fulfill(status=200, content_type='application/json', body=json.dumps({'text':'Backend engineer needed to build Java services. Python is a preferred skill.'}))
            await page.route('**/api/job-url', fake_import)
            page.once('dialog', lambda dialog: dialog.accept())
            async with page.expect_response('**/api/job-url'):
                await page.locator('#import-job').click()
            assert imports == [{'url':'https://example.com/job'}]
            await page.locator('#consent').check()
            requests = []
            async def fake_tailor(route):
                requests.append(json.loads(route.request.post_data))
                result = {'resume':'Avery Example\n\nEXPERIENCE\nBuilt reliable Java services.',
                          'sections':[{'heading':'Experience','lines':[{'text':'Built reliable Java services.','evidence':['Built reliable Java services for customers.']}]}],
                          'changes':[{'before':'Built reliable Java services for customers.','after':'Built reliable Java services.','reason':'Focuses on backend experience.'}],
                          'alignment':[{'point':'Java work relates to the role.','resume_evidence':'Built reliable Java services for customers.','job_evidence':'build Java services'}],
                          'suggestions':[{'skill':'Python','job_evidence':'Python is a preferred skill.'}],
                          'warnings':['Some suggestions could not be verified and were omitted.']}
                await route.fulfill(status=200, content_type='application/json', body=json.dumps(result))
            await page.route('**/api/tailor', fake_tailor)
            async with page.expect_response('**/api/tailor'):
                await page.locator('#generate').click()
            await expect(page.locator('#result-badge')).to_have_text('Ready to review')
            await expect(page.locator('#generate-status')).to_contain_text('omitted')
            assert await page.locator('#api-key').input_value() == ''
            storage = await page.evaluate('JSON.stringify({local: {...localStorage}, session: {...sessionStorage}, cookies: document.cookie})')
            assert 'dummy-key-never-real' not in storage
            assert requests[0]['consent'] is True and 'Avery Example' in requests[0]['resume']
            assert requests[0]['verification'] == application.make_verification('gemini', 'dummy-key-never-real', requests[0]['model'], '')
            assert requests[0]['use_saved'] is True and 'api_key' not in requests[0]
            assert 'Python' not in await page.locator('#tailored-text').input_value()
            await expect(page.locator('#download-pdf')).to_be_disabled()
            await page.get_by_label('I have Python').check()
            await page.locator('#add-skills').click()
            assert 'Python' in await page.locator('#tailored-text').input_value()
            await page.locator('#confirm').check()
            async with page.expect_download() as pdf_event:
                await page.locator('#download-pdf').click()
            pdf_path = tmp_path / 'resume.pdf'
            await (await pdf_event.value).save_as(pdf_path)
            assert 'Python' in '\n'.join(p.extract_text() for p in PdfReader(pdf_path).pages)
            async with page.expect_download() as word_event:
                await page.locator('#download-docx').click()
            word_path = tmp_path / 'resume.docx'
            await (await word_event.value).save_as(word_path)
            assert 'Python' in '\n'.join(p.text for p in Document(word_path).paragraphs)
            await page.locator('#tailored-text').fill('Avery Example\n\nA reviewed and edited resume for the role.')
            await expect(page.locator('#download-pdf')).to_be_disabled()
            await page.locator('#open-settings').click()
            assert await page.locator('#api-key').input_value() == ''
            assert 'saved key' in await page.locator('#api-key').get_attribute('placeholder')
            await page.locator('#toggle-key').click()
            assert await page.locator('#api-key').get_attribute('type') == 'text'
            await page.select_option('#provider', 'openai')
            assert await page.locator('#api-key').input_value() == ''
            assert await page.locator('#api-key').get_attribute('type') == 'password'
            await expect(page.locator('#save-settings')).to_be_disabled()
            await page.locator('#cancel-settings').click()
            await expect(page.locator('#active-provider')).to_have_text('Gemini connected')
            await page.locator('#open-settings').click()
            assert await page.locator('#api-key').input_value() == ''
            await page.locator('#cancel-settings').click()
            await page.set_viewport_size({'width': 375, 'height': 812})
            assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')

            reopened = await browser.new_page()
            browser_checks = []
            async def capture_check(route):
                browser_checks.append(json.loads(route.request.post_data))
                await route.continue_()
            await reopened.route('**/api/test-provider', capture_check)
            await reopened.goto(f'http://127.0.0.1:{port}/')
            await expect(reopened.locator('#active-provider')).to_have_text('Gemini saved')
            await expect(reopened.locator('#generate')).to_be_disabled()
            before_test = len(checks)
            fail_next[0] = True
            await reopened.locator('#test-saved-connection').click()
            await expect(reopened.locator('#generate-status')).to_contain_text('Connection failed')
            await expect(reopened.locator('#generate')).to_be_disabled()
            assert saved_file.exists()
            await reopened.locator('#test-saved-connection').click()
            await expect(reopened.locator('#active-provider')).to_have_text('Gemini connected')
            await expect(reopened.locator('#generate')).to_be_enabled()
            assert len(checks) == before_test + 2
            assert checks[-1]['api_key'] == 'dummy-key-never-real'
            assert browser_checks[-1]['use_saved'] is True and 'api_key' not in browser_checks[-1]
            await reopened.locator('#resume-text').fill('Avery Example: Built reliable Java services for customers.')
            await reopened.locator('#job-text').fill('Backend engineer needed to build Java services. Python is a preferred skill.')
            await reopened.locator('#consent').check()
            async def expired_connection(route):
                await route.fulfill(status=400, content_type='application/json', body='{"detail":"Test this AI connection before tailoring your resume."}')
            await reopened.route('**/api/tailor', expired_connection)
            await reopened.locator('#generate').click()
            await expect(reopened.locator('#test-saved-connection')).to_be_visible()
            await expect(reopened.locator('#generate')).to_be_disabled()
            await reopened.locator('#test-saved-connection').click()
            await expect(reopened.locator('#generate')).to_be_enabled()
            await reopened.locator('#open-settings').click()
            assert await reopened.locator('#api-key').input_value() == ''
            await reopened.select_option('#model', 'custom')
            await reopened.locator('#custom-model').fill('gemini-custom-model')
            await reopened.locator('#test-provider').click()
            await expect(reopened.locator('#save-settings')).to_be_enabled()
            reopened.once('dialog', lambda dialog: dialog.accept())
            await reopened.locator('#save-settings').click()
            await expect(reopened.locator('#settings-dialog')).not_to_be_visible()
            assert json.loads(saved_file.read_text())['model'] == 'gemini-custom-model'
            assert json.loads(saved_file.read_text())['api_key'] == 'dummy-key-never-real'
            await reopened.locator('#open-settings').click()
            await reopened.locator('#api-key').fill('replacement-dummy-key')
            await expect(reopened.locator('#save-settings')).to_be_disabled()
            await reopened.locator('#test-provider').click()
            await expect(reopened.locator('#save-settings')).to_be_enabled()
            reopened.once('dialog', lambda dialog: dialog.accept())
            await reopened.locator('#save-settings').click()
            await expect(reopened.locator('#settings-dialog')).not_to_be_visible()
            assert json.loads(saved_file.read_text())['api_key'] == 'replacement-dummy-key'
            await reopened.locator('#open-settings').click()
            assert await reopened.locator('#api-key').input_value() == ''
            reopened.once('dialog', lambda dialog: dialog.accept())
            await reopened.locator('#forget-settings').click()
            await expect(reopened.locator('#saved-settings')).not_to_be_visible()
            assert not saved_file.exists()
            await reopened.locator('#cancel-settings').click()
            await expect(reopened.locator('#generate')).to_be_disabled()

            session_only = await browser.new_page()
            await session_only.goto(f'http://127.0.0.1:{port}/')
            await session_only.wait_for_selector('#provider option[value="openai"]', state='attached')
            await session_only.locator('#open-settings').click()
            await session_only.locator('#api-key').fill('dummy-session-key-only')
            await session_only.locator('#remember-settings').uncheck()
            await session_only.locator('#test-provider').click()
            await expect(session_only.locator('#save-settings')).to_be_enabled()
            await session_only.locator('#save-settings').click()
            await expect(session_only.locator('#generate')).to_be_enabled()
            assert not saved_file.exists()
            await session_only.reload()
            await expect(session_only.locator('#generate')).to_be_disabled()
            await browser.close()
    finally:
        server.should_exit = True
        await task
        listener.close()
