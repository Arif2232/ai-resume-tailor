"""Start the local app on an available loopback port."""

import socket
import threading
import webbrowser

import uvicorn


def main():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    url = f'http://127.0.0.1:{port}/'
    server = uvicorn.Server(uvicorn.Config('resume_tailor.server:app', host='127.0.0.1', port=port,
                                          log_level='warning', access_log=False))
    stopped = threading.Event()

    def open_when_ready():
        for _ in range(300):
            if stopped.wait(0.1):
                return
            if server.started:
                webbrowser.open(url)
                return

    thread = threading.Thread(target=open_when_ready, daemon=True)
    thread.start()
    print(f'Opening {url}\nKeep this terminal open while using the app. Press Ctrl+C to stop.', flush=True)
    try:
        server.run(sockets=[listener])
    finally:
        stopped.set()
        listener.close()


if __name__ == '__main__':
    main()
