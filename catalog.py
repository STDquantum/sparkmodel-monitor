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


def build_catalog():
    DOCS.mkdir(exist_ok=True)
    products = []
    for number, (product_id, listing) in enumerate(monitor.fetch_all().items(), start=1):
        fields, properties, images = parse_detail(monitor.request(listing["url"]))
        local_images = [download_image(url, product_id, index) for index, url in enumerate(images, start=1)]
        products.append({
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
            "availability": fields.get("availability", ""),
        })
        print(f"[{number}] {products[-1]['name']} ({len(local_images)} image(s))")
    catalog = {"generated_at": datetime.now(timezone.utc).isoformat(), "products": products}
    (DOCS / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(products)} products in {DOCS}")


if __name__ == "__main__":
    build_catalog()
