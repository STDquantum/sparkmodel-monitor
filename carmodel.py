"""Carmodel Burago listings and detail pages (independent of Shopware)."""
import json
import re
import time
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request
from html import unescape
from urllib.parse import urlencode, urljoin, urlsplit, parse_qs

BASE = 'https://www.carmodel.com'
SEARCHES = {
    '2025': ('AMR25', 'A525', 'RB21', 'SF-25', 'MCL39', 'W16'),
    '2026': ('AMR26', 'A526', 'SF-26', 'RB22', 'MCL40', 'W17', 'VCARB-03', 'VF-26', 'FW48', 'MAC-26', 'R26'),
}

def search_url(model, mode='', page=1):
    keyword = f'burago F1 {model}' + (' Audi' if model == 'R26' else '')
    return BASE + '/search?' + urlencode(dict(keyword=keyword, scale='all', country='', nuOb=mode, resultsPerPage=120, page=page))

SOURCES = tuple(search_url(model) for models in SEARCHES.values() for model in models)

def request(url):
    # Carmodel sets session cookies during its language/currency redirects.
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    for attempt in range(5):
        try:
            with opener.open(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-GB,en;q=0.9'}), timeout=45) as response:
                return response.read().decode('utf-8')
        except Exception:
            if attempt == 4:
                raise
            time.sleep(min(10 * 2 ** attempt, 60))

def text(html):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', html)).split())

def parse_listing(html, year, model, mode=''):
    rows = {}
    cards = re.findall(r'<article\b[^>]*\bclass="[^"]*prod-card\b[^>]*>(.*?)</article>', html, re.S)
    for card in cards:
        title = re.search(r'<p\b[^>]*class="product-description"[^>]*>(.*?)</p>', card, re.S)
        if not title:
            raise ValueError('Carmodel card has no product title')
        name = text(title[1])
        if not re.search(r'\b' + year + r'\b', name):
            continue
        href = re.search(r'href="([^"]+)"', title[1])[1]
        parts = urlsplit(href).path.strip('/').split('/')
        if parts[0].lower() != 'burago':
            continue
        pid = 'burago-' + parts[-1]
        image = re.search(r'<img\b[^>]*class="product-img"[^>]*src="([^"]+)"', card)
        price = re.search(r'class="actual-price"[^>]*>(.*?)</span>', card, re.S)
        release = re.search(r'class="[^"]*coming-soon-label"\s*title="([^"]+)"', card)
        rows[pid] = dict(product_id=pid, source='carmodel', manufacturer='Burago', name=name,
                         url=urljoin(BASE, href), product_number=parts[1].upper(), scale=parts[2].replace('-', '/'),
                         year=year, model=model, image_url=unescape(image[1]) if image else '',
                         availability='Coming soon' if mode == 'coming_soon' or 'coming-soon-label' in card else ('Available' if 'btn-available' in card else 'Catalogue'),
                         release=unescape(release[1]) if release else '', price=text(price[1]).replace('€','') if price else '')
    links = []
    for attrs in re.findall(r'<a\b([^>]+)>', html):
        href = re.search(r'href="([^"]+)"', attrs)
        if href and ('showAllItems' in attrs or 'page-link' in attrs):
            url = urljoin(BASE, unescape(href[1]))
            q = parse_qs(urlsplit(url).query)
            if urlsplit(url).path == '/search' and q.get('keyword') == parse_qs(urlsplit(search_url(model)).query)['keyword']:
                links.append(search_url(model, q.get('nuOb', [''])[0], int(q.get('page', ['1'])[0])))
    if not cards and not re.search(r'did not return any results|no (?:items|results|products)|0 (?:items|results|products)|No models', html, re.I):
        raise ValueError('Unrecognized Carmodel search response')
    return rows, links

def fetch(year, model):
    queue = [search_url(model), search_url(model, 'coming_soon')]
    seen, products = set(), {}
    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        mode = parse_qs(urlsplit(url).query).get('nuOb', [''])[0]
        html = request(url)
        rows, links = parse_listing(html, year, model, mode)
        products.update(rows)
        queue.extend(link for link in links if link not in seen)
    print(f'Carmodel {year} {model}: {len(products)} products, {len(seen)} result pages', flush=True)
    return products

def parse_detail(html):
    payloads = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    data = next((obj for raw in payloads for obj in [json.loads(raw)] if isinstance(obj, dict) and obj.get('@type') == 'Product'), None)
    if data is None:
        raise ValueError('Carmodel Product structured data missing')
    properties = {}
    details_table = re.search(r'<table[^>]*class="product-features[^"]*"[^>]*>.*?</table>', html, re.S)
    if not details_table:
        raise ValueError('Carmodel properties table missing')
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', details_table[0], re.S):
        key = re.search(r'<th\b[^>]*>(.*?)</th>', row, re.S)
        if not key:
            continue
        values = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S)
        if values:
            properties[text(key[1]).rstrip(':')] = text(values[-1])
    properties['Product number'] = data['serialNumber'].strip()
    properties['Manufacturer'] = 'Burago'
    properties.setdefault('Scale', data.get('size', ''))
    images = list(dict.fromkeys(unescape(url) for url in re.findall(r'<a\b[^>]*data-fancybox-group="gallery"[^>]*href="([^"]+)"', html)))
    if not images:
        raise ValueError('Carmodel detail gallery missing')
    return data, properties, images

def build_product(product_id, listing):
    import catalog
    data, props, images = parse_detail(request(listing['url']))
    if props['Product number'].upper() != listing['product_number'].upper():
        raise ValueError('Carmodel listing/detail manufacturer code mismatch')
    props['Year'] = listing['year']
    props['Model code'] = listing['model']
    if listing.get('release'):
        props['Expected release'] = listing['release']
    offer = data.get('offers', {})
    return dict(id=product_id, name=listing['name'], url=listing['url'],
                images=catalog.download_unique_images(images, product_id, workers=4), properties=props,
                description=data.get('description', ''), brand='Burago', price=str(offer.get('price', '')),
                currency=offer.get('priceCurrency', 'EUR'), gtin=data.get('gtin', ''), weight='', length='',
                availability=listing['availability'], image_urls=images)
