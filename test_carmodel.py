import unittest
from pathlib import Path
from unittest.mock import patch
import carmodel

class CarmodelTests(unittest.TestCase):
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

