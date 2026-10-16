import json
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import monitor, carmodel
from paths import TEMP

def main(argv=None):
    parser = argparse.ArgumentParser(description='Refresh Burago locally without contacting other model sources or sending notifications.')
    parser.add_argument('--resume', action='store_true', help='Reuse previously cached search results')
    parser.add_argument('--build', action='store_true', help='Also update the local catalogue, images and update history')
    args = parser.parse_args(argv)
    old=monitor.load_state()
    if old is None:
        raise RuntimeError('Existing state.json is required; no files were changed')
    products={k:v for k,v in old.items() if v.get('source')!='carmodel'}
    cache=TEMP / 'carmodel'; cache.mkdir(parents=True,exist_ok=True)
    def fetch_cached(y,m):
        path=cache / (y+'-'+m+'.json')
        if args.resume and path.exists(): return json.loads(path.read_text(encoding='utf-8'))
        rows=carmodel.fetch(y,m)
        path.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
        return rows
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(fetch_cached,y,m) for y,models in carmodel.SEARCHES.items() for m in models]
        for job in as_completed(jobs):
            products.update(job.result())
    added,changed,removed=monitor.compare(old,products)
    if any((added, changed, removed)):
        monitor.save_state(products, (x["product_id"] for x in added), (x["product_id"] for x in changed), (x["product_id"] for x in removed))
    print('TOTAL BURAGO',sum(x.get('source')=='carmodel' for x in products.values()))
    if args.build:
        import catalog, updates
        os.environ['CARMODEL_ENABLED'] = 'true'
        pending = catalog.refresh_ids(products, {p['id']: p for p in catalog.load_catalog()}, {'added': [x['product_id'] for x in added], 'changed': [x['product_id'] for x in changed]})
        if not any((added, changed, removed)) and not any(products[pid].get('source') == 'carmodel' for pid in pending):
            print('No Burago changes; existing snapshot, catalogue and history kept')
            return
        catalog.build_catalog(source='carmodel')
        updates.publish()

if __name__ == "__main__":
    main()
