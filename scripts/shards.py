"""Publish a shared TOC, small search indexes and cacheable detail shards."""
import hashlib
import json

from paths import DOCS
import manual_products


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
        temporary.write_text(text, encoding='utf-8')
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
    for start in range(0, len(products), 48):
        batch = products[start:start + 48]
        path = shard('catalog', {'products': batch})
        for product in batch:
            summaries.append({**{key: value for key, value in product.items() if key != 'image_urls'}, 'images': product.get('images', [])[:1],
                              'image_count': len(product.get('images', [])), '_shard': path})
    brands = {str(p['id']): p.get('brand', '') for p in products}
    runs = []
    for run in history['updates']:
        path = shard('updates', run)
        entries = []
        for entry in run.get('entries', []):
            summary = {key: entry[key] for key in ('id', 'name', 'url', 'type', 'product_number', 'scale', 'brand') if key in entry}
            summary['brand'] = entry.get('brand') or brands.get(str(entry.get('id')), '')
            summary['_search'] = ' '.join(str(field.get(key, '')) for field in entry.get('fields', []) for key in ('field', 'before', 'after'))
            entries.append(summary)
        runs.append({'date': run['date'], '_shard': path, 'entries': entries})
    catalog_index = shard('indexes', pack({'generated_at': catalog.get('generated_at'), 'products': summaries}))
    updates_index = shard('indexes', pack({'updates': runs}))
    write_data(DOCS / 'toc.json', {'version': 1, 'catalog': catalog_index, 'updates': updates_index,
                                 'product_count': len(products), 'run_count': len(runs)})
    print(f'Published TOC: {len(products)} products, {len(runs)} update groups')


if __name__ == '__main__':
    publish()
