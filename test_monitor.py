import unittest

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


if __name__ == "__main__":
    unittest.main()
