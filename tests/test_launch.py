import threading

from resume_tailor import __main__ as launcher


def test_launcher_binds_to_loopback_and_opens_the_local_url(monkeypatch):
    opened = []
    called = threading.Event()
    def open_browser(url):
        opened.append(url)
        called.set()
    class FakeServer:
        started = True
        def __init__(self, config): self.config = config
        def run(self, sockets):
            assert sockets[0].getsockname()[0] == '127.0.0.1'
            assert called.wait(2)
    monkeypatch.setattr(launcher.uvicorn, 'Server', FakeServer)
    monkeypatch.setattr(launcher.webbrowser, 'open', open_browser)
    launcher.main()
    assert len(opened) == 1 and opened[0].startswith('http://127.0.0.1:')
