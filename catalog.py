#!/usr/bin/env python3
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import monitor

DOCS = Path(__file__).with_name("docs")
IMAGES = DOCS / "images"
CATALOG_FILE = DOCS / "catalog.json"


class DetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.capture = None
        self.text = []
        self.description_depth = None
        self.properties_depth = None
        self.property_key = None
        self.properties = {}
        self.fields = {}
        self.images = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "")
        if tag == "div":
            self.div_depth += 1
            if "product-detail-description-text" in classes:
                self.description_depth = self.div_depth
                self.capture = "description"
                self.text = []
            if "product-detail-properties" in classes:
                self.properties_depth = self.div_depth
        if tag == "meta" and attributes.get("itemprop") in {
            "price", "priceCurrency", "gtin13", "weight", "length", "url"
        }:
            self.fields[attributes["itemprop"]] = attributes.get("content", "")
        elif tag == "link" and attributes.get("itemprop") == "availability":
            self.fields["availability"] = attributes.get("href", "").rsplit("/", 1)[-1]
        elif tag == "h1" and "product-detail-name" in classes:
            self.capture = "name"
            self.text = []
        elif tag == "img" and "gallery-slider-image" in classes:
            url = attributes.get("data-full-image") or attributes.get("src")
            if url and url not in self.images:
                self.images.append(url)
        elif self.properties_depth is not None and tag in {"th", "td"}:
            self.capture = tag
            self.text = []
        elif tag == "br" and self.capture:
            self.text.append(" ")

    def handle_data(self, data):
        if self.capture:
            self.text.append(data)

    def handle_endtag(self, tag):
        if (tag == "h1" and self.capture == "name") or (tag in {"th", "td"} and self.capture == tag):
            value = " ".join("".join(self.text).split())
            if tag == "h1":
                self.fields["name"] = value
            elif tag == "th":
                self.property_key = value
            elif self.property_key:
                self.properties[self.property_key] = value
                self.property_key = None
            self.capture = None
        if tag == "div":
            if self.description_depth == self.div_depth:
                self.fields["description"] = " ".join("".join(self.text).split())
                self.description_depth = None
                self.capture = None
            if self.properties_depth == self.div_depth:
                self.properties_depth = None
            self.div_depth -= 1


def parse_detail(html):
    parser = DetailParser()
    parser.feed(html)
    return parser.fields, parser.properties, parser.images


def download_image(url, product_id, index):
    suffix = Path(urlsplit(url).path).suffix or ".webp"
    relative = Path("images") / f"{product_id}-{index}{suffix}"
    destination = DOCS / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": monitor.USER_AGENT}), timeout=90) as response:
                destination.write_bytes(response.read())
            break
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    return relative.as_posix()


def load_catalog():
    if not CATALOG_FILE.exists():
        return []
    with CATALOG_FILE.open(encoding="utf-8") as file:
        return json.load(file).get("products", [])


def load_snapshot():
    with monitor.STATE_FILE.open(encoding="utf-8") as file:
        state = json.load(file)
    if state.get("sources") != list(monitor.SOURCE_URLS):
        raise RuntimeError("State sources do not match the current monitor configuration")
    return state


def remove_images(product_id, keep=()):
    keep = set(keep)
    for image in IMAGES.glob(f"{product_id}-*"):
        if image.name not in keep:
            image.unlink()


def remove_unused_images(products):
    used = {Path(image).name for product in products for image in product.get("images", ())}
    if IMAGES.exists():
        for image in IMAGES.iterdir():
            if image.is_file() and image.name not in used:
                image.unlink()


def refresh_ids(items, products, changes):
    changed = set(changes.get("added", ())) | set(changes.get("changed", ()))
    return sorted((changed | (set(items) - set(products))) & set(items))


def build_product(product_id, listing):
    fields, properties, images = parse_detail(monitor.request(listing["url"]))
    local_images = [download_image(url, product_id, index) for index, url in enumerate(images, start=1)]
    remove_images(product_id, (Path(image).name for image in local_images))
    return {
        "id": product_id,
        "name": fields.get("name") or listing["name"],
        "url": listing["url"],
        "images": local_images,
        "properties": properties,
        "description": fields.get("description", ""),
        "brand": properties.get("Manufacturer", "Spark"),
        "price": fields.get("price", ""),
        "currency": fields.get("priceCurrency", "EUR"),
        "gtin": fields.get("gtin13", ""),
        "weight": fields.get("weight", ""),
        "length": fields.get("length", ""),
        "availability": listing.get("availability", fields.get("availability", "")),
    }


def build_catalog():
    DOCS.mkdir(exist_ok=True)
    state = load_snapshot()
    items = state["items"]
    products = {product["id"]: product for product in load_catalog()}
    removed = set(state.get("changes", {}).get("removed", ())) | (set(products) - set(items))
    for product_id in removed:
        products.pop(product_id, None)
        remove_images(product_id)
    for number, product_id in enumerate(refresh_ids(items, products, state.get("changes", {})), start=1):
        products[product_id] = build_product(product_id, items[product_id])
        print(f"[{number}] {products[product_id]['name']} ({len(products[product_id]['images'])} image(s))")
    catalog = {"generated_at": datetime.now(timezone.utc).isoformat(), "products": list(products.values())}
    CATALOG_FILE.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    remove_unused_images(catalog["products"])
    print(f"Updated {len(products)} products in {DOCS}")


if __name__ == "__main__":
    build_catalog()
