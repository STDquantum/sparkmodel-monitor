import json
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import monitor, carmodel

def main(argv=None):
    parser = argparse.ArgumentParser(description='Refresh Burago locally without contacting other model sources or sending notifications.')
    parser.add_argument('--resume', action='store_true', help='Reuse previously cached search results')
    parser.add_argument('--build', action='store_true', help='Also update the local catalogue, images and update history')
    args = parser.parse_args(argv)
    old=monitor.load_state()
    if old is None:
        raise RuntimeError('Existing state.json is required; no files were changed')
    products={k:v for k,v in old.items() if v.get('source')!='carmodel'}
    report=[]
    cache=Path(__file__).parent / 'tmp' / 'carmodel'; cache.mkdir(parents=True,exist_ok=True)
    def fetch_cached(y,m):
        path=cache / (y+'-'+m+'.json')
        if args.resume and path.exists(): return json.loads(path.read_text(encoding='utf-8'))
        rows=carmodel.fetch(y,m)
        path.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
        return rows
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(fetch_cached,y,m):(y,m) for y,models in carmodel.SEARCHES.items() for m in models}
        for job in as_completed(jobs):
            y,m=jobs[job]; rows=job.result();products.update(rows);report.append(dict(year=y,model=m,count=len(rows),coming_soon=sum(x['availability']=='Coming soon' for x in rows.values())))
    Path(__file__).with_name('carmodel-coverage.json').write_text(json.dumps(sorted(report,key=lambda x:(x['year'],x['model'])),indent=2),encoding='utf-8')
    added,changed,removed=monitor.compare(old,products)
    monitor.save_state(products, (x["product_id"] for x in added), (x["product_id"] for x in changed), (x["product_id"] for x in removed))
    print('TOTAL BURAGO',sum(x.get('source')=='carmodel' for x in products.values()))
    if args.build:
        import catalog, updates
        os.environ['CARMODEL_ENABLED'] = 'true'
        catalog.build_catalog(source='carmodel')
        updates.publish()

if __name__ == "__main__":
    main()
