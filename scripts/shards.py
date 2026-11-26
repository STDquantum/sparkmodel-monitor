"""Publish a shared TOC, small search indexes and cacheable detail shards."""
import hashlib
import json
import re

from paths import DOCS
import manual_products

SHARD_BYTES = 512 * 1024


def payload_bytes(data):
    return len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) + 1


def batches(items, wrap, limit=SHARD_BYTES):
    """Bound the actual UTF-8 JSON size, keeping individual records intact."""
    start = 0
    while start < len(items):
        low, high = start + 1, len(items)
        if payload_bytes(wrap(items[start:low])) > limit:
            yield items[start:low]  # One oversized record must remain readable.
            start = low
            continue
        while low < high:
            middle = (low + high + 1) // 2
            if payload_bytes(wrap(items[start:middle])) <= limit:
                low = middle
            else:
                high = middle - 1
        yield items[start:low]
        start = low


def index_parts(items, key, metadata=None):
    wrap = lambda batch: pack({**(metadata or {}), key: batch})
    return [shard('indexes', wrap(batch)) for batch in batches(items, wrap)] or [shard('indexes', wrap([]))]


def pack(data):
    """Intern repeated strings in search indexes (names, URLs and properties)."""
    strings, positions = [], {}

    def encode(value):
        if isinstance(value, str):
            if value not in positions:
                positions[value] = len(strings)
                strings.append(value)
            return positions[value]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return {'$number': value}
        if isinstance(value, list):
            return [encode(item) for item in value]
        result = {key: encode(item) for key, item in value.items()}
        return {'$object': result} if '$number' in result or '$object' in result else result

    encoded = encode(data)
    return {'strings': strings, 'packed': encoded}


def write_data(path, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    path.parent.mkdir(parents=True, exist_ok=True)
    key = path.relative_to(DOCS).as_posix()
    contents = {
        path: payload + '\n',
        path.with_suffix('.js'): 'window.DATA_SHARDS=window.DATA_SHARDS||{};window.DATA_SHARDS['
        + json.dumps(key) + ']=' + payload.replace('</', '<\\/') + ';\n',
    }
    for destination, text in contents.items():
        if destination.exists() and destination.read_text(encoding='utf-8') == text:
            continue
        temporary = destination.with_suffix(destination.suffix + '.tmp')
        temporary.write_text(text, encoding='utf-8', newline='\n')
        temporary.replace(destination)
    return key


def shard(kind, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    name = hashlib.sha256(payload).hexdigest()[:20]
    return write_data(DOCS / 'data' / kind / (name + '.json'), data)


def publish():
    catalog = manual_products.merge(
        json.loads((DOCS / 'catalog.json').read_text(encoding='utf-8')),
        manual_products.read_data())
    history = json.loads((DOCS / 'updates.json').read_text(encoding='utf-8')) if (DOCS / 'updates.json').exists() else {'updates': []}
    products = catalog['products']
    summaries = []
    for batch in batches(products, lambda batch: {'products': batch}):
        path = shard('catalog', {'products': batch})
        for product in batch:
            summaries.append({**{key: value for key, value in product.items() if key != 'image_urls'}, 'images': product.get('images', [])[:1],
                              'image_count': len(product.get('images', [])), '_shard': path})
    brands = {str(p['id']): p.get('brand', '') for p in products}
    runs = [{key: value for key, value in run.items() if key != 'entries'} for run in history['updates']]
    records = [(run_index, entry) for run_index, run in enumerate(history['updates']) for entry in run.get('entries', [])]
    entries = []
    for batch in batches(records, lambda batch: {'entries': [entry for _, entry in batch]}):
        path = shard('updates', {'entries': [entry for _, entry in batch]})
        for offset, (run_index, entry) in enumerate(batch):
            summary = {key: entry[key] for key in ('id', 'name', 'url', 'type', 'product_number', 'scale', 'brand') if key in entry}
            summary['brand'] = entry.get('brand') or brands.get(str(entry.get('id')), '')
            summary['_search'] = ' '.join(str(field.get(key, '')) for field in entry.get('fields', []) for key in ('field', 'before', 'after'))
            summary.update(_run=run_index, _shard=path, _offset=offset)
            entries.append(summary)
    catalog_index = index_parts(summaries, 'products', {'generated_at': catalog.get('generated_at')})
    updates_index = index_parts(entries, 'entries', {'runs': runs})
    write_data(DOCS / 'toc.json', {'version': 2, 'shard_bytes': SHARD_BYTES,
                                 'catalog': catalog_index, 'updates': updates_index,
                                 'product_count': len(products), 'run_count': len(runs)})
    keep = set(catalog_index + updates_index)
    keep.update(product['_shard'] for product in summaries)
    keep.update(entry['_shard'] for entry in entries)
    for kind in ('catalog', 'updates', 'indexes'):
        for path in (DOCS / 'data' / kind).glob('*'):
            if re.fullmatch(r'[0-9a-f]{20}\.(json|js)', path.name):
                if path.with_suffix('.json').relative_to(DOCS).as_posix() not in keep:
                    path.unlink()
    print(f'Published TOC: {len(products)} products, {len(runs)} update groups')


if __name__ == '__main__':
    publish()
