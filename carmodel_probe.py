"""Read-only Carmodel connectivity checks; no notifications or snapshot writes."""
import re
import argparse
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
            visible = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', body, flags=re.S | re.I)
            print('  response:', carmodel.text(visible)[:400], flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
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
    if args.browser:
        print('\nPROFILE: browser HTTP connection', flush=True)
        from curl_cffi import requests
        with requests.Session(impersonate='chrome') as session:
            for url in (carmodel.BASE + '/', carmodel.search_url('RB21')):
                try:
                    response = session.get(url, timeout=20)
                    print(f'{url}: HTTP {response.status_code}, challenge={response.headers.get("cf-mitigated")}, cards={len(re.findall(r"<article", response.text))}', flush=True)
                except Exception as error:
                    print(type(error).__name__, str(error)[:300], flush=True)
                time.sleep(2)
        print('\nPROFILE: Chromium with JavaScript', flush=True)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(locale='en-GB')
            page = context.new_page()
            try:
                response = page.goto(carmodel.search_url('RB21'), wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(25000)
                print(f'Chromium: initial HTTP {response.status}, title={page.title()}, cards={page.locator("article.prod-card").count()}', flush=True)
                print('  page text:', page.locator('body').inner_text()[:400], flush=True)
            except Exception as error:
                print(type(error).__name__, str(error)[:300], flush=True)
            finally:
                browser.close()

if __name__ == '__main__':
    main()
