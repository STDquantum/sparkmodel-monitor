import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, unquote

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
CACHE = HERE / 'index-cache.json'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, stderr=subprocess.PIPE)

def number(p):
    return str((p.get('properties') or {}).get('Product number') or '').strip()

def key(p):
    # Case and incidental surrounding whitespace do not distinguish a product number.
    n = number(p)
    return n.upper() if n else ''

def group(products):
    result = defaultdict(list)
    for p in products:
        k = key(p)
        # Never silently merge products without a product number.
        if not k:
            k = '无货号:' + str(p.get('id') or hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
        result[k].append(p)
    return dict(result)

def build():
    head = git('rev-parse', 'HEAD').decode().strip()
    current = (ROOT / 'docs/catalog.json').read_bytes()
    stamp = hashlib.sha256(current).hexdigest()
    if CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding='utf-8'))
            if cached.get('format') == 4 and cached.get('head') == head and cached.get('stamp') == stamp:
                return cached
        except (ValueError, OSError):
            pass
    print('正在读取 Git 历史，首次运行可能需要一些时间……', flush=True)
    lines = git('log', '--first-parent', '--reverse', '--format=%H%x09%cI', '--', 'docs/catalog.json', 'docs/images', 'docs/manual-images').decode().splitlines()
    histories = defaultdict(list)
    previous = {}
    prior_commit = None
    for i, line in enumerate(lines):
        commit, date = line.split('\t', 1)
        try:
            snapshot = json.loads(git('show', commit + ':docs/catalog.json'))
            now = group(snapshot.get('products', []))
        except (subprocess.CalledProcessError, ValueError, AttributeError) as e:
            print('跳过无法读取的快照', commit[:8], e, flush=True)
            continue
        changed = set()
        if prior_commit:
            changed = set(git('diff', '--name-only', '-z', prior_commit, commit, '--', 'docs').decode('utf-8').split('\0'))
        for k in previous.keys() | now.keys():
            old, new = previous.get(k), now.get(k)
            image_changed = bool(new and any('docs/' + path in changed for p in new for path in p.get('images', []) if isinstance(path, str)))
            if old != new or image_changed:
                histories[k].append({'commit': commit, 'date': date, 'products': new or [], 'reason': '出现' if old is None else '移除' if new is None else '更新'})
        previous, prior_commit = now, commit
        if (i + 1) % 25 == 0:
            print('已处理 %s / %s 个快照' % (i + 1, len(lines)), flush=True)
    # Include local unsaved catalog changes without modifying the repository.
    now = group(json.loads(current).get('products', []))
    for k in previous.keys() | now.keys():
        old, new = previous.get(k), now.get(k)
        if old != new:
            histories[k].append({'commit': 'WORKTREE', 'date': '', 'products': new or [], 'reason': '本地变更' if new else '本地移除'})
    data = {'format': 4, 'head': head, 'stamp': stamp, 'snapshots': len(lines), 'histories': histories}
    CACHE.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return data

DATA = None
class Handler(BaseHTTPRequestHandler):
    def send(self, data, mime='application/json; charset=utf-8', status=200):
        self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(data))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        u = urlsplit(self.path)
        if u.path == '/api/list':
            items = []
            for k, events in DATA['histories'].items():
                last = events[-1]; latest = next((e for e in reversed(events) if e['products']), last)
                p = latest['products'][0] if latest['products'] else {}
                items.append({'key': k, 'id': p.get('id', ''), 'name': p.get('name', ''), 'url': p.get('url', ''), 'brand': p.get('brand', ''), 'scale': (p.get('properties') or {}).get('Scale', ''), 'product_number': k, 'type': 'removed' if not last['products'] else 'added' if last['reason'] == '出现' else 'changed', 'search_text': json.dumps([e['products'] for e in events], ensure_ascii=False), 'count': len(events), 'removed': not bool(last['products']), 'date': latest['date'], 'image': (p.get('images') or [''])[0], 'commit': latest['commit'], 'duplicates': len(latest['products'])})
            self.send(json.dumps({'items': items, 'snapshots': DATA['snapshots']}, ensure_ascii=False).encode())
        elif u.path == '/api/history':
            k = parse_qs(u.query).get('key', [''])[0]
            self.send(json.dumps(DATA['histories'].get(k, []), ensure_ascii=False).encode())
        elif u.path == '/image':
            q = parse_qs(u.query); rev = q.get('rev', [''])[0]; path = q.get('path', [''])[0]
            if not (rev == 'WORKTREE' or re.fullmatch(r'[0-9a-f]{40}', rev)) or not re.fullmatch(r'(?:images|manual-images)/[^\\:]+', path) or '..' in path.split('/'):
                return self.send(b'Invalid image', 'text/plain', 400)
            try:
                if rev == 'WORKTREE':
                    target = (ROOT / 'docs' / path).resolve()
                    if not target.is_relative_to((ROOT / 'docs').resolve()): raise ValueError('invalid path')
                    content = target.read_bytes()
                else: content = git('show', rev + ':docs/' + path)
                self.send(content, 'image/webp' if path.lower().endswith('.webp') else mimetypes.guess_type(path)[0] or 'application/octet-stream')
            except (OSError, ValueError, subprocess.CalledProcessError): self.send(b'Image unavailable', 'text/plain', 404)
        elif u.path in ('/', '/index.html'):
            self.send((HERE / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        else: self.send(b'Not found', 'text/plain', 404)

def main():
    global DATA
    DATA = build()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = 'http://127.0.0.1:%s/' % server.server_port
    print('历史浏览器已启动：' + url + '\n关闭此窗口即可停止。', flush=True)
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__ == '__main__': main()


