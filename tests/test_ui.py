import asyncio
import io
import json
import socket

import uvicorn
from docx import Document
from playwright.async_api import async_playwright, expect
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from resume_tailor.server import app


def example_pdf():
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(50, 750, 'Avery Example - Software Engineer')
    page.drawString(50, 730, 'Built reliable Java services for customers.')
    page.save()
    return output.getvalue()


async def test_browser_flow_reviews_suggestions_and_exports_without_real_ai(tmp_path):
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
            await page.locator('#resume-file').set_input_files({'name':'resume.pdf','mimeType':'application/pdf','buffer':example_pdf()})
            await expect(page.locator('#resume-status')).to_contain_text('Resume loaded')
            assert 'Avery Example' in await page.locator('#resume-text').input_value()
            await page.locator('#job-text').fill('Backend engineer needed to build Java services. Python is a preferred skill.')
            await page.select_option('#provider', 'gemini')
            await expect(page.locator('#provider-note')).to_contain_text('free-tier')
            await page.locator('#api-key').fill('dummy-key-never-real')
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
            checks = []
            async def fake_check(route):
                checks.append(json.loads(route.request.post_data))
                await route.fulfill(status=200, content_type='application/json', body='{"message":"Connected."}')
            await page.route('**/api/test-provider', fake_check)
            async with page.expect_response('**/api/test-provider'):
                await page.locator('#test-provider').click()
            await expect(page.locator('#connection-status')).to_contain_text('Connected')
            assert set(checks[0]) == {'provider','model','api_key','workspace_id'} and checks[0]['provider'] == 'gemini'
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
            assert await page.locator('#api-key').input_value() == 'dummy-key-never-real'
            storage = await page.evaluate('JSON.stringify({local: {...localStorage}, session: {...sessionStorage}, cookies: document.cookie})')
            assert 'dummy-key-never-real' not in storage
            assert requests[0]['consent'] is True and 'Avery Example' in requests[0]['resume']
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
            await page.locator('#toggle-key').click()
            assert await page.locator('#api-key').get_attribute('type') == 'text'
            await page.select_option('#provider', 'openai')
            assert await page.locator('#api-key').input_value() == ''
            assert await page.locator('#api-key').get_attribute('type') == 'password'
            await page.set_viewport_size({'width': 375, 'height': 812})
            assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            await browser.close()
    finally:
        server.should_exit = True
        await task
        listener.close()
