import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from catalog import parse_detail, refresh_ids, remove_images, remove_unused_images
from monitor import TEAM_SEARCHES, availability_label, build_message, compare, ferrari_match, parse_listing


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

    def test_change_message_includes_product_number_and_scale(self):
        message = build_message(1, [{
            "name": "F1 Car",
            "url": "https://example.test/item",
            "product_number": "S9367",
            "scale": "1/43",
        }], [], [])
        self.assertIn("货号：S9367；比例：1/43", message)

    def test_availability_change_is_parsed_and_reported(self):
        html = '''<div data-aria-live-text="Showing 1 out of 1 products.">
        <div class="product-box" data-product-information="{&quot;id&quot;:&quot;id-1&quot;}">
        <a class="product-name" href="https://example.test/item" title="F1 car"></a>
        <img class="product-image" src="https://example.test/cover.webp">
        <div class="product-detail-delivery-information"><p>Pre-order available</p></div></div></div>'''
        items, _ = parse_listing(html)
        self.assertEqual(items[0]["availability"], "Pre-order available")
        _, changed, _ = compare(
            {"id-1": items[0] | {"availability": "In stock"}},
            {"id-1": items[0]},
        )
        self.assertEqual(changed[0]["changes"]["availability"], ("In stock", "Pre-order available"))
        message = build_message(1, [], changed, [])
        self.assertIn("Availability：In stock → Pre-order available", message)
        self.assertIn("封面变化 **0**，Availability 变化 **1**", message)

    def test_availability_labels(self):
        self.assertEqual(availability_label("Available immediately"), "Available")
        self.assertEqual(availability_label("Not available – pre-orders possible"), "Pre-order")
        self.assertEqual(availability_label("Limited stock"), "Limited stock")

    def test_listing_parser(self):
        html = '''<div data-aria-live-text="Showing 1 out of 1 products.">
        <div class="card product-box" data-product-information="{&quot;id&quot;:&quot;id-1&quot;,&quot;name&quot;:&quot;F1&quot;}">
        <a class="product-name" href="https://example.test/item" title="F1 car"></a>
        <img class="product-image is-cover" src="https://example.test/cover.webp"></div></div>'''
        items, total = parse_listing(html)
        self.assertEqual(total, 1)
        self.assertEqual(items, [{"product_id": "id-1", "name": "F1 car", "url": "https://example.test/item", "image_url": "https://example.test/cover.webp"}])

    def test_search_listing_total(self):
        html = '''<h1>7 products found for &quot;BWT Alpine Formula One Team&quot;</h1>
        <div class="product-box" data-product-information="{&quot;id&quot;:&quot;id-1&quot;}">
        <a class="product-name" href="https://example.test/item" title="F1 car"></a>
        <img class="product-image" src="https://example.test/cover.webp"></div>'''
        items, total = parse_listing(html)
        self.assertEqual(total, 7)
        self.assertEqual(len(items), 1)

    def test_team_sources_and_ferrari_filter(self):
        self.assertEqual(len(TEAM_SEARCHES), 11)
        self.assertTrue(ferrari_match("Scuderia Ferrari HP SF-26 No.16"))
        self.assertTrue(ferrari_match("Ferrari SF-26 No.44"))
        self.assertFalse(ferrari_match("Ferrari 499P"))

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

    def test_catalog_refreshes_only_changed_and_missing_products(self):
        items = {"kept": {}, "changed": {}, "added": {}, "missing": {}}
        products = {"kept": {}, "changed": {}, "obsolete": {}}
        changes = {"added": ["added"], "changed": ["changed"], "removed": ["obsolete"]}
        self.assertEqual(refresh_ids(items, products, changes), ["added", "changed", "missing"])

    def test_remove_images_keeps_current_files(self):
        with TemporaryDirectory() as directory:
            images = Path(directory)
            (images / "item-1.webp").touch()
            (images / "item-2.webp").touch()
            with patch("catalog.IMAGES", images):
                remove_images("item", {"item-1.webp"})
            self.assertTrue((images / "item-1.webp").exists())
            self.assertFalse((images / "item-2.webp").exists())

    def test_remove_unused_images(self):
        with TemporaryDirectory() as directory:
            images = Path(directory)
            (images / "used.webp").touch()
            (images / "orphan.webp").touch()
            with patch("catalog.IMAGES", images):
                remove_unused_images([{"images": ["images/used.webp"]}])
            self.assertTrue((images / "used.webp").exists())
            self.assertFalse((images / "orphan.webp").exists())


if __name__ == "__main__":
    unittest.main()
