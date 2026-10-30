"""Static preview of the web shell, with no backend and no changes to the running app.

python3 web/tests/serve_preview.py [port]        # then open http://127.0.0.1:8877
"""
import functools
import http.server
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    """/sw.js and /manifest.webmanifest live under static/ in this repo."""

    def do_GET(self):
        if self.path.startswith('/api/'):
            self.send_error(503, 'Isolated preview: no backend')
            return
        if self.path in ('/sw.js', '/manifest.webmanifest'):
            self.path = '/static' + self.path
        super().do_GET()

    def log_message(self, format, *args):
        pass


def make_server(port=0, directory=WEB):
    handler = functools.partial(PreviewHandler, directory=str(directory))
    return http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)


if __name__ == '__main__':
    server = make_server(int(sys.argv[1]) if len(sys.argv) > 1 else 8877)
    host, port = server.server_address[:2]
    print(f'Preview estatica em http://{host}:{port} (Ctrl+C encerra)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
