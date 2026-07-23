import unittest

from monitor import compare


class CompareTest(unittest.TestCase):
    def test_add_cover_change_and_remove(self):
        old = {
            "kept": {"photo_id": "1", "primary_image_url": "a"},
            "changed": {"photo_id": "2", "primary_image_url": "b"},
            "removed": {"photo_id": "3", "primary_image_url": "c"},
        }
        new = {
            "kept": {"photo_id": "1", "primary_image_url": "a"},
            "changed": {"photo_id": "4", "primary_image_url": "d"},
            "added": {"photo_id": "5", "primary_image_url": "e"},
        }
        added, changed, removed = compare(old, new)
        self.assertEqual([x["product_id"] for x in added], ["added"])
        self.assertEqual([x["product_id"] for x in changed], ["changed"])
        self.assertEqual([x["product_id"] for x in removed], ["removed"])


if __name__ == "__main__":
    unittest.main()
