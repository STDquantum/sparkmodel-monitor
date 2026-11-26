import argparse
import os
import sys
import monitor, carmodel

def main(argv=None):
    parser = argparse.ArgumentParser(description='Refresh Burago locally without contacting other model sources or sending notifications.')
    parser.add_argument('--build', action='store_true', help='Also update the local catalogue, images and update history')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--browser', action='store_true', help='Use a visible browser for all Carmodel requests')
    mode.add_argument('--http-only', action='store_true', help='Disable automatic visible-browser fallback')
    parser.add_argument('--browser-channel', choices=('chrome', 'msedge'), default='chrome', help='Installed browser to open (default: chrome)')
    parser.add_argument('--verification-timeout', type=int, default=120, help='Seconds to wait for a verified product page (default: 120)')
    args = parser.parse_args(argv)
    if args.verification_timeout <= 0:
        parser.error('--verification-timeout must be positive')
    try:
        if args.http_only:
            refresh(args)
        else:
            from carmodel_browser import BrowserSession
            with BrowserSession(force=args.browser, channel=args.browser_channel, verification_timeout=args.verification_timeout) as session:
                carmodel.browser_session = session
                try:
                    refresh(args)
                finally:
                    carmodel.browser_session = None
        return 0
    except carmodel.SourceUnavailable as error:
        print(f'\n比美高采集已停止：{error}', file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print('\n已取消比美高采集。', flush=True)
        return 130


def refresh(args):
    old=monitor.load_state()
    if old is None:
        raise RuntimeError('Existing state.json is required; no files were changed')
    products={k:v for k,v in old.items() if v.get('source')!='carmodel'}
    # A single visible tab must stay on the verification page until the user finishes.
    for year, models in carmodel.SEARCHES.items():
        for model in models:
            products.update(carmodel.fetch(year, model))
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
    sys.exit(main())
