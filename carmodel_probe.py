"""Read-only Carmodel connectivity checks; no notifications or snapshot writes."""
import re
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

import carmodel

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Upgrade-Insecure-Requests': '1',
}

def probe(opener, url, headers):
    start = time.monotonic()
    try:
        response = opener.open(Request(url, headers=headers), timeout=20)
    except HTTPError as error:
        response = error
    except Exception as error:
        print(f'{url}: {type(error).__name__}: {error}', flush=True)
        return
    with response:
        body = response.read().decode('utf-8', errors='replace')
        print(f'{url}: HTTP {response.code}, final={response.url}, elapsed={time.monotonic()-start:.1f}s, cards={len(re.findall(r"<article", body))}', flush=True)
        for key in ('Server', 'Content-Type', 'cf-mitigated', 'Retry-After'):
            if response.headers.get(key):
                print(f'  {key}: {response.headers[key]}', flush=True)
        if response.code != 200:
            print('  response:', carmodel.text(body)[:700], flush=True)

def main():
    for label, headers, warm in (
        ('existing headers', {'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-GB,en;q=0.9'}, False),
        ('browser headers', BROWSER_HEADERS, False),
        ('browser headers with homepage cookies', BROWSER_HEADERS, True),
    ):
        print('\nPROFILE:', label, flush=True)
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        if warm:
            probe(opener, carmodel.BASE + '/', headers)
            time.sleep(2)
        probe(opener, carmodel.search_url('RB21'), headers)
        time.sleep(2)

if __name__ == '__main__':
    main()
