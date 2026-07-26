import unittest

from catalog import parse_detail
from monitor import compare, parse_listing


class CompareTest(unittest.TestCase):
    def test_add_cover_change_and_remove(self):
        old = {
            "kept": {"image_url": "a"},
            "changed": {"image_url": "b"},
            "removed": {"image_url": "c"},
        }
        new = {
            "kept": {"image_url": "a"},
            "changed": {"image_url": "d"},
            "added": {"image_url": "e"},
        }
        added, changed, removed = compare(old, new)
        self.assertEqual([x["product_id"] for x in added], ["added"])
        self.assertEqual([x["product_id"] for x in changed], ["changed"])
        self.assertEqual([x["product_id"] for x in removed], ["removed"])

    def test_listing_parser(self):
        html = '''<div data-aria-live-text="Showing 1 out of 1 products.">
        <div class="card product-box" data-product-information="{&quot;id&quot;:&quot;id-1&quot;,&quot;name&quot;:&quot;F1&quot;}">
        <a class="product-name" href="https://example.test/item" title="F1 car"></a>
        <img class="product-image is-cover" src="https://example.test/cover.webp"></div></div>'''
        items, total = parse_listing(html)
        self.assertEqual(total, 1)
        self.assertEqual(items, [{"product_id": "id-1", "name": "F1 car", "url": "https://example.test/item", "image_url": "https://example.test/cover.webp"}])

    def test_detail_parser(self):
        html = '''<h1 class="product-detail-name">F1 Car</h1><meta itemprop="price" content="19.95">
        <div class="product-detail-properties"><th>Scale</th><td>1/43</td></div>
        <div class="product-detail-description-text">A <strong>fast</strong> car</div>
        <img class="gallery-slider-image" data-full-image="https://example.test/a.webp">'''
        fields, properties, images = parse_detail(html)
        self.assertEqual(fields["name"], "F1 Car")
        self.assertEqual(fields["price"], "19.95")
        self.assertEqual(fields["description"], "A fast car")
        self.assertEqual(properties, {"Scale": "1/43"})
        self.assertEqual(images, ["https://example.test/a.webp"])


if __name__ == "__main__":
    unittest.main()
