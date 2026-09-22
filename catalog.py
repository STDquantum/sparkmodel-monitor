#!/usr/bin/env python3
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


class LooksmartDetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.capture = None
        self.capture_depth = None
        self.gallery_depth = None
        self.text = []
        self.fields = {}
        self.images = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        if tag == "div":
            self.div_depth += 1
            if "woocommerce-product-gallery__wrapper" in classes:
                self.gallery_depth = self.div_depth
            if "woocommerce-product-details__short-description" in classes:
                self.capture = "description"
                self.capture_depth = self.div_depth
                self.text = []
        if tag == "h1" and ("product_title" in classes or "entry-title" in classes):
            self.capture = "name"
            self.text = []
        elif tag == "span" and "sku" in classes:
            self.capture = "sku"
            self.text = []
        elif tag == "a" and self.gallery_depth is not None:
            href = attributes.get("href", "")
            if self.div_depth and "/wp-content/uploads/" in href and href not in self.images:
                self.images.append(href)
        elif tag == "img" and self.gallery_depth is not None:
            url = attributes.get("data-large_image") or attributes.get("data-src") or attributes.get("src")
            if url and url not in self.images:
                self.images.append(url)
        elif tag == "br" and self.capture:
            self.text.append(" ")

    def handle_data(self, data):
        if self.capture:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self.capture == "name":
            self.fields["name"] = " ".join("".join(self.text).split())
            self.capture = None
        elif tag == "span" and self.capture == "sku":
            self.fields["sku"] = " ".join("".join(self.text).split())
            self.capture = None
        if tag == "div":
            if self.capture == "description" and self.div_depth == self.capture_depth:
                description = " ".join("".join(self.text).split())
                self.fields["description"] = description
                code = re.search(r"Product\s+Code\s*:\s*([\w-]+)", description, re.I)
                color = re.search(r"Color\s*:\s*(.+?)(?=\s+A(?:vailability|valiability)\s*:|$)", description, re.I)
                availability = re.search(r"A(?:vailability|valiability)\s*:\s*(.+?)(?=\s+CHECK OTHER|$)", description, re.I)
                if code:
                    self.fields["sku"] = code.group(1)
                if color:
                    self.fields["color"] = color.group(1).strip()
                if availability:
                    self.fields["availability"] = availability.group(1).strip()
                self.capture = None
                self.capture_depth = None
            if self.gallery_depth == self.div_depth:
                self.gallery_depth = None
            self.div_depth -= 1


def parse_looksmart_detail(html):
    parser = LooksmartDetailParser()
    parser.feed(html)
    return parser.fields, parser.images


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
    source = listing.get("source", "sparkmodelshop")
    if source == "sparkmodel":
        source_id = listing.get("source_id") or product_id.removeprefix("spark-2025-")
        detail = json.loads(monitor.request(f"{monitor.SPARK_API_URL}/{source_id}"))
        image_payload = json.loads(monitor.request(f"{monitor.SPARK_API_URL}/{source_id}/images?sort=position"))
        images = [
            f"https://minimax.fra1.cdn.digitaloceanspaces.com/published/{filename}-desktop-2x.webp"
            for filename in image_payload.get("data", []) if filename
        ]
        if not images and listing.get("image_url"):
            images = [listing["image_url"]]
        local_images = [download_image(url, product_id, index) for index, url in enumerate(images, start=1)]
        remove_images(product_id, (Path(image).name for image in local_images))
        properties = {
            "Manufacturer": detail.get("manufacturer_name") or listing.get("manufacturer", ""),
            "Material": detail.get("material_name", ""),
            "Model": detail.get("model_fullname") or detail.get("model_name", ""),
            "Scale": (detail.get("scale", {}).get("name") or listing.get("scale", "")).replace(":", "/"),
            "Year": str(detail.get("year") or listing.get("year", "")),
            "Product number": detail.get("code") or listing.get("product_number", ""),
            "Driver": detail.get("ranking_driver_names", ""),
            "Grand Prix": detail.get("ranking_competition_name", ""),
            "Result": detail.get("ranking_rank_name", ""),
        }
        return {
            "id": product_id,
            "name": monitor.clean_product_name(detail.get("name") or listing["name"]),
            "url": listing["url"],
            "images": local_images,
            "properties": {key: value for key, value in properties.items() if value},
            "description": "",
            "brand": "Spark",
            "price": "",
            "currency": "",
            "gtin": "",
            "weight": "",
            "length": "",
            "availability": listing.get("availability", ""),
        }
    if source == "looksmart":
        fields, images = parse_looksmart_detail(monitor.request(listing["url"]))
        if not images and listing.get("image_url"):
            images = [listing["image_url"]]
        local_images = [download_image(url, product_id, index) for index, url in enumerate(images, start=1)]
        remove_images(product_id, (Path(image).name for image in local_images))
        scale_match = re.search(r"\b1[:/]\s*(5|8|12|18|43|64)\b", fields.get("name") or listing["name"], re.I)
        scale = listing.get("scale") or (f"1/{scale_match.group(1)}" if scale_match else "")
        properties = {
            "Manufacturer": "Ferrari",
            "Model": "SF-25",
            "Scale": scale,
            "Year": "2025",
            "Product number": fields.get("sku") or listing.get("product_number", ""),
            "Color": fields.get("color", ""),
        }
        return {
            "id": product_id,
            "name": fields.get("name") or listing["name"],
            "url": listing["url"],
            "images": local_images,
            "properties": {key: value for key, value in properties.items() if value},
            "description": fields.get("description", ""),
            "brand": "Looksmart",
            "price": "",
            "currency": "",
            "gtin": "",
            "weight": "",
            "length": "",
            "availability": fields.get("availability") or listing.get("availability", ""),
        }
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
    product_ids = refresh_ids(items, products, state.get("changes", {}))
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(build_product, product_id, items[product_id]): product_id for product_id in product_ids}
        for number, future in enumerate(as_completed(futures), start=1):
            product_id = futures[future]
            products[product_id] = future.result()
            print(f"[{number}/{len(product_ids)}] {products[product_id]['name']} ({len(products[product_id]['images'])} image(s))", flush=True)
    catalog = {"generated_at": datetime.now(timezone.utc).isoformat(), "products": [products[key] for key in sorted(products)]}
    CATALOG_FILE.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    remove_unused_images(catalog["products"])
    print(f"Updated {len(products)} products in {DOCS}")


if __name__ == "__main__":
    build_catalog()
