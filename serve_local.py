"""Local catalog and date annotation server (standard library only)."""
import argparse
import json
import re
import threading
import webbrowser
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import manual_products

DOCS = Path(__file__).resolve().parent / 'docs'
TIMES = DOCS / 'product-times.js'
LOCK = threading.Lock()

def read_times():
    source = TIMES.read_text(encoding='utf-8-sig')
    match = re.fullmatch(r'\s*window\.PRODUCT_TIMES\s*=\s*(.*?)\s*;?\s*', source, re.DOTALL)
    if not match:
        raise ValueError('Invalid product-times.js')
    data = json.loads(match.group(1))
    if not isinstance(data, dict):
        raise ValueError('Date data must be an object')
    return data

def write_times(data):
    temporary = TIMES.with_suffix('.js.tmp')
    temporary.write_text('window.PRODUCT_TIMES=' + json.dumps(data, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')
    temporary.replace(TIMES)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_POST(self):
        if self.path not in ('/api/product-times', '/api/products'):
            self.send_error(404)
            return
        # Only same-origin browser requests can change local files.
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self.send_error(403)
            return
        if self.headers.get('Content-Type') != 'application/json':
            self.send_error(415)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            limit = 64 * 1024 * 1024 if self.path == '/api/products' else 4096
            if not 0 < length <= limit:
                raise ValueError('Invalid request size')
            payload = json.loads(self.rfile.read(length))
            if self.path == '/api/products':
                with LOCK:
                    result = manual_products.save_product(payload)
                body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            model = payload['model']
            if not isinstance(model, str) or not model.strip() or len(model) > 200:
                raise ValueError('Invalid product number')
            values = {}
            for field in ('published', 'shipped'):
                value = payload.get(field, '')
                if not isinstance(value, str):
                    raise ValueError('Invalid date')
                if value:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                        raise ValueError('Use YYYY-MM-DD')
                    date.fromisoformat(value)
                values[field] = value
            with LOCK:
                data = read_times()
                data[model.strip()] = values
                write_times(data)
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ValueError, KeyError, TypeError) as error:
            self.send_error(400, str(error))
        except OSError:
            self.send_error(500, 'Could not save date file')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=410)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--page', choices=['both', 'index.html', 'annotate.html', 'product-editor.html'], default='both')
    args = parser.parse_args()
    with LOCK:
        read_times()
        manual_products.sync_hashes()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    pages = ['annotate.html', 'product-editor.html'] if args.page == 'both' else [args.page]
    for page in pages:
        url = f'http://127.0.0.1:{args.port}/{page}'
        print(url, flush=True)
        if not args.no_browser:
            webbrowser.open_new_tab(url)
    server.serve_forever()
