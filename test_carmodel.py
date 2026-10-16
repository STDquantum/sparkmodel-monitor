import unittest
import os
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from contextlib import ExitStack
import carmodel

class CarmodelTests(unittest.TestCase):
    def test_cloud_disabled_keeps_all_burago_without_requests(self):
        import monitor
        previous = {'burago-legacy': {'source': 'carmodel', 'name': 'Existing product'}}
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'CARMODEL_ENABLED': 'false', 'MINICHAMPS_ENABLED': 'false'}))
            stack.enter_context(patch.object(monitor, 'load_state', return_value=previous))
            fetch = stack.enter_context(patch.object(carmodel, 'fetch'))
            for name in ('SPARK_2025_SEARCHES', 'SPARK_2026_SEARCHES', 'SPARK_SHOP_2025_SEARCHES', 'LOOKSMART_SEARCHES'):
                stack.enter_context(patch.object(monitor, name, ()))
            stack.enter_context(patch.object(monitor, 'apply_looksmart_shop_covers'))
            self.assertEqual(monitor.fetch_all(), previous)
            fetch.assert_not_called()

    def test_cloud_catalogue_skips_missing_and_changed_burago(self):
        import catalog
        items = {'burago-missing': {'source': 'carmodel'}, 'burago-changed': {'source': 'carmodel'}, 'spark-new': {'source': 'sparkmodel'}}
        with patch.dict(os.environ, {'CARMODEL_ENABLED': 'false'}):
            self.assertEqual(catalog.refresh_ids(items, {'burago-changed': {}}, {'changed': ['burago-changed']}), ['spark-new'])
        with patch.dict(os.environ, {'CARMODEL_ENABLED': 'true'}):
            self.assertEqual(catalog.refresh_ids(items, {'burago-changed': {}}, {'changed': ['burago-changed']}), sorted(items))

    def test_access_denied_stops_without_retry(self):
        for status in (401, 403, 429):
            with self.subTest(status=status), patch.object(carmodel, 'build_opener') as build, patch.object(carmodel.time, 'sleep') as sleep:
                build.return_value.open.side_effect = HTTPError('https://www.carmodel.com/search', status, 'Denied', {}, None)
                with self.assertRaises(carmodel.SourceUnavailable):
                    carmodel.request(carmodel.search_url('RB21'))
                self.assertEqual(build.return_value.open.call_count, 1)
                sleep.assert_not_called()

    def test_transient_failure_has_bounded_retries(self):
        with patch.object(carmodel, 'build_opener') as build, patch.object(carmodel.time, 'sleep') as sleep:
            build.return_value.open.side_effect = URLError('connection failed')
            with self.assertRaises(carmodel.SourceUnavailable):
                carmodel.request(carmodel.search_url('RB21'))
            self.assertEqual(build.return_value.open.call_count, 3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])
            self.assertEqual(build.return_value.open.call_args.kwargs['timeout'], 20)

    def test_cloudflare_challenge_is_reported(self):
        with patch.object(carmodel, 'build_opener') as build:
            build.return_value.open.side_effect = HTTPError('https://www.carmodel.com/search', 403, 'Forbidden', {'cf-mitigated': 'challenge'}, None)
            with self.assertRaisesRegex(carmodel.SourceUnavailable, 'Cloudflare browser challenge'):
                carmodel.request(carmodel.search_url('RB21'))

    def test_transient_failure_can_recover(self):
        with patch.object(carmodel, 'build_opener') as build, patch.object(carmodel.time, 'sleep'):
            response = build.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'page html'
            build.return_value.open.side_effect = [URLError('temporary'), build.return_value.open.return_value]
            self.assertEqual(carmodel.request(carmodel.search_url('RB21')), 'page html')

    def test_source_outage_keeps_snapshot_and_other_brands_continue(self):
        import monitor
        previous = {f'burago-{model}': dict(source='carmodel', year=year, model=model, name=model)
                    for year, models in carmodel.SEARCHES.items() for model in models}
        with ExitStack() as stack:
            stack.enter_context(patch.object(monitor, 'load_state', return_value=previous))
            fetch = stack.enter_context(patch.object(carmodel, 'fetch', side_effect=carmodel.SourceUnavailable('403')))
            for name in ('SPARK_2026_SEARCHES', 'SPARK_SHOP_2025_SEARCHES', 'LOOKSMART_SEARCHES', 'MINICHAMPS_SEARCHES'):
                stack.enter_context(patch.object(monitor, name, ()))
            stack.enter_context(patch.object(monitor, 'SPARK_2025_SEARCHES', ('RB21',)))
            spark = stack.enter_context(patch.object(monitor, 'fetch_spark_2025', return_value={'spark-fresh': {'source': 'sparkmodel', 'name': 'fresh'}}))
            stack.enter_context(patch.object(monitor, 'fetch_minichamps_2025', return_value={}))
            stack.enter_context(patch.object(monitor, 'apply_looksmart_shop_covers'))
            stack.enter_context(patch.object(monitor, 'deduplicate_spark_products', side_effect=lambda rows: rows))
            for run in range(2):
                current = monitor.fetch_all()
                self.assertEqual(current, dict(previous, **{'spark-fresh': {'source': 'sparkmodel', 'name': 'fresh'}}))
                self.assertEqual(fetch.call_count, run + 1)
                self.assertEqual(spark.call_count, run + 1)

    def card(self, year='2025'):
        return f'''<article class="prod-card" id="1"><p class="product-description"><a href="/burago/code/1-43/red-bull/title/1">RED BULL RB21 {year}</a></p><img class="product-img" src="https://bucket.carmodel.com/a.webp"><span class="coming-soon-label" title="Available within quarter 4/2026">QTR</span></article>'''

    def test_year_and_coming_soon(self):
        rows,_=carmodel.parse_listing(self.card() + self.card('2024'), '2025','RB21')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows['burago-1']['availability'],'Coming soon')
        self.assertEqual(rows['burago-1']['product_number'],'CODE')
        self.assertEqual(rows['burago-1']['scale'],'1/43')

    def test_show_all_and_pagination_are_followed(self):
        main=carmodel.search_url('RB21')
        coming=carmodel.search_url('RB21','coming_soon')
        page2=carmodel.search_url('RB21','coming_soon',2)
        pages={main:self.card()+f'<a class="showAllItems" href="{coming}">Show all</a>',coming:self.card()+f'<a class="page-link" href="{page2}">2</a>',page2:self.card().replace('/title/1','/title/2')}
        with patch.object(carmodel,'request',side_effect=lambda url:pages[url]) as req:
            rows=carmodel.fetch('2025','RB21')
        self.assertEqual(len(rows),2)
        self.assertEqual(req.call_count,3)

    def test_detail_properties_and_gallery(self):
        html='''<script type="application/ld+json">{"@type":"Product","serialNumber":"ABC","size":"1/43"}</script><table class="product-features table"><tr><th>Year:</th><td>2025</td></tr></table><table><tr><th>MB</th><td>unrelated glossary</td></tr></table><a data-fancybox-group="gallery" href="https://bucket.carmodel.com/images/cm-lg/1.jpg"></a><a data-fancybox-group="gallery" href="https://bucket.carmodel.com/images/cm-lg/1.jpg"></a><a data-fancybox-group="gallery" href="https://bucket.carmodel.com/images/cm-lg/2.jpg"></a>'''
        _,props,images=carmodel.parse_detail(html)
        self.assertNotIn('MB',props)
        self.assertEqual(len(images),2)
        self.assertEqual(props['Product number'],'ABC')

    def test_zero_results_remains_a_valid_query(self):
        rows,links=carmodel.parse_listing('Your search did not return any results.', '2026','VF-26')
        self.assertEqual(rows,{})
        self.assertEqual(links,[])

    def test_bad_responses_fail(self):
        with self.assertRaises(ValueError): carmodel.parse_listing('<h1>Blocked</h1>','2025','RB21')
        with self.assertRaises(ValueError): carmodel.parse_detail('<h1>Blocked</h1>')

    def test_parallel_images_deduplicate_content(self):
        import uuid
        import catalog
        root=Path(__file__).parent / 'tmp' / ('image-test-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        try:
            def download(url, pid, index):
                path=root / f'{index}.jpg'
                path.write_bytes(b'same' if index < 3 else b'different')
                return path.name
            with patch.object(catalog,'DOCS',root), patch.object(catalog,'IMAGES',root), patch.object(catalog,'download_image',side_effect=download), patch.object(catalog,'remove_images'):
                result=catalog.download_unique_images(['a','b','c'], 'test', workers=3)
            self.assertEqual(result,['1.jpg','3.jpg'])
            self.assertFalse((root/'2.jpg').exists())
        finally:
            for path in root.iterdir(): path.unlink()
            root.rmdir()

    def test_query_contract(self):
        self.assertEqual(len(carmodel.SOURCES),17)
        self.assertIn('burago+F1+R26+Audi',carmodel.search_url('R26'))

if __name__=='__main__': unittest.main()

