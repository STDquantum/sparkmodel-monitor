"""Persistent manual overrides and content-based image merging."""
import base64
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path

from paths import DOCS
FILE = DOCS / 'manual-products.js'

def read_data():
    if not FILE.exists():
        return {'entries': {}, 'imageHashes': {}}
    match = re.fullmatch(r'\s*window\.MANUAL_PRODUCT_DATA\s*=\s*(.*?)\s*;?\s*', FILE.read_text(encoding='utf-8-sig'), re.S)
    if not match:
        raise ValueError('Invalid manual-products.js')
    return json.loads(match.group(1))

def image_hash(src):
    path = (DOCS / src).resolve()
    if not path.is_relative_to(DOCS.resolve()) or not path.is_file():
        return ''
    return hashlib.sha256(path.read_bytes()).hexdigest()

def sync_hashes(catalog=None, data=None):
    catalog = catalog or json.loads((DOCS / 'catalog.json').read_text(encoding='utf-8'))
    data = data if data is not None else read_data()
    sources = {src for p in catalog['products'] for src in p.get('images', [])}
    sources.update(src for entry in data['entries'].values() for src in entry.get('images', []))
    data['imageHashes'] = {src: image_hash(src) for src in sorted(sources)}
    temp = FILE.with_suffix('.js.tmp')
    temp.write_text('window.MANUAL_PRODUCT_DATA=' + json.dumps(data, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')
    temp.replace(FILE)
    return data

def merge(catalog, data):
    result = copy.deepcopy(catalog)
    products = {str(p['id']): p for p in result['products']}
    for product_id, entry in data['entries'].items():
        if product_id not in products:
            products[product_id] = {'id': product_id, 'images': [], 'properties': {}}
        product = products[product_id]
        product.update(entry['fields'])
        product['properties'] = {**product.get('properties', {}), **entry['properties']}
        for key in entry.get('hiddenProperties', []):
            product['properties'].pop(key, None)
        images, seen = [], set()
        # Keep manually uploaded copies first, so an identical automatic copy cannot displace them.
        for src in entry.get('images', []) + product.get('images', []):
            digest = data['imageHashes'].get(src) or src
            if digest in entry.get('hiddenHashes', []) or digest in seen:
                continue
            images.append(src)
            seen.add(digest)
        product['images'] = images
    result['products'] = list(products.values())
    return result

def save_product(payload):
    catalog = json.loads((DOCS / 'catalog.json').read_text(encoding='utf-8'))
    data = read_data()
    effective = merge(catalog, data)['products']
    product_id = str(payload.get('id') or '')
    if product_id and product_id not in {str(p['id']) for p in effective}:
        raise ValueError('商品不存在')
    fields = {}
    for field in ('manufacturer', 'model', 'availability', 'year', 'scale'):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError(field + ' 为必填项')
        fields[field] = value.strip()
    if not re.fullmatch(r'\d{4}', fields['year']) or not 1900 <= int(fields['year']) <= 2100:
        raise ValueError('年份无效')
    if not re.fullmatch(r'1/\d{1,4}', fields['scale']):
        raise ValueError('比例无效')
    if fields['availability'] not in {'Available', 'Pre-order', 'Catalogue'}:
        raise ValueError('Availability 无效')
    if any(str(p['id']) != product_id and str(p.get('properties', {}).get('Product number', p.get('model', ''))).strip() == fields['model'] for p in effective):
        raise ValueError('货号已存在，请修改已有商品')
    product_id = product_id or 'manual-' + uuid.uuid4().hex
    entry = copy.deepcopy(data['entries'].get(product_id, {'images': [], 'hiddenHashes': []}))
    name = payload.get('name', '').strip() or f"{fields['manufacturer']} {fields['model']} {fields['year']}"
    url = payload.get('url', '').strip()
    if url and not re.match(r'^https?://', url, re.I):
        raise ValueError('商品链接须为 http 或 https')
    entry['fields'] = {'name': name, 'url': url, 'description': str(payload.get('description', '')), 'brand': fields['manufacturer'], 'model': fields['model'], 'availability': fields['availability']}
    entry['properties'] = {'Year': fields['year'], 'Manufacturer': fields['manufacturer'], 'Scale': fields['scale'], 'Product number': fields['model']}
    current = next((p for p in effective if str(p['id']) == product_id), {'images': [], 'properties': {}})
    reserved = {'Year', 'Manufacturer', 'Scale', 'Product number', 'Availability', 'Properties', '__proto__', 'constructor', 'prototype'}
    extras = payload.get('extraProperties', {k: v for k, v in current.get('properties', {}).items() if k not in reserved})
    if not isinstance(extras, dict) or len(extras) > 100:
        raise ValueError('其他详情项格式无效，最多 100 项')
    normalized_extras = {}
    for key, value in extras.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 200 or key.strip() in reserved:
            raise ValueError('详情项名称无效或与固定字段重复')
        if not isinstance(value, str) or len(value) > 10000:
            raise ValueError('详情项内容无效')
        key = key.strip()
        if key in normalized_extras:
            raise ValueError('详情项名称不能重复')
        normalized_extras[key] = value.strip()
    entry['properties'].update(normalized_extras)
    entry['hiddenProperties'] = list(set(entry.get('hiddenProperties', [])) | {k for k in current.get('properties', {}) if k not in reserved and k not in normalized_extras})
    entry['hiddenProperties'] = [k for k in entry['hiddenProperties'] if k not in normalized_extras]
    removed = payload.get('removeImages', [])
    for src in removed:
        if src not in current['images']:
            raise ValueError('不能删除其他商品的图片')
        digest = image_hash(src)
        if digest and digest not in entry['hiddenHashes']:
            entry['hiddenHashes'].append(digest)
        entry['images'] = [image for image in entry['images'] if image != src]
    uploads = payload.get('uploads', [])
    if len(uploads) > 30:
        raise ValueError('每次最多添加 30 张图片')
    decoded = []
    for upload in uploads:
        raw = base64.b64decode(upload['data'], validate=True)
        if not raw or len(raw) > 15 * 1024 * 1024:
            raise ValueError('每张图片不能超过 15 MB')
        if raw.startswith(b'\x89PNG\r\n\x1a\n'): ext = '.png'
        elif raw.startswith(b'\xff\xd8\xff'): ext = '.jpg'
        elif raw[:6] in (b'GIF87a', b'GIF89a'): ext = '.gif'
        elif raw[:4] == b'RIFF' and raw[8:12] == b'WEBP': ext = '.webp'
        else: raise ValueError('只支持 PNG、JPEG、GIF、WebP 图片')
        digest = hashlib.sha256(raw).hexdigest()
        src = 'manual-images/' + digest + ext
        decoded.append((src, raw, digest))
    for src, raw, digest in decoded:
        path = DOCS / src
        path.parent.mkdir(exist_ok=True)
        if not path.exists(): path.write_bytes(raw)
        entry['hiddenHashes'] = [h for h in entry['hiddenHashes'] if h != digest]
        if src not in entry['images']: entry['images'].append(src)
    data['entries'][product_id] = entry
    data = sync_hashes(catalog, data)
    return {'id': product_id, 'catalog': merge(catalog, data)}
