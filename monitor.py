#!/usr/bin/env python3
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape as html_unescape
from http.client import IncompleteRead
from html.parser import HTMLParser
from pathlib import Path
from http.cookiejar import CookieJar
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.request import build_opener, HTTPCookieProcessor

SEARCH_URL = "https://www.sparkmodelshop.com/de/en/search"
SPARK_API_URL = "https://rapi.sparkmodel.com/products"
SPARK_SITE_URL = "https://www.sparkmodel.com"
LOOKSMART_SEARCH_URL = "https://looksmartmodels.com/?s=SF-25&post_type=product&dgwt_wcas=1"
MINICHAMPS_BASE_URL = "https://www.minichamps.de/"
MINICHAMPS_URL = "https://www.minichamps.de/en/search"
MINICHAMPS_WIDGET_URL = "https://www.minichamps.de/en/widgets/search"
MINICHAMPS_SEARCHES = ("W17", "VF-26", "AMR26", "VCARB 03", "MAC-26", "A526", "Audi R26", "RB22", "FW48", "MCL40")
MINICHAMPS_MODEL_PATTERNS = {
    "W17": r"\bW17\b", "VF-26": r"\bVF-26\b", "AMR26": r"\bAMR26\b",
    "VCARB 03": r"\bVCARB\s*03\b", "MAC-26": r"\bMAC-26\b", "A526": r"\bA526\b",
    "Audi R26": r"\bR26\b", "RB22": r"\bRB22\b", "FW48": r"\bFW48\b", "MCL40": r"\bMCL40\b",
}
TEAM_SEARCHES = (
    "BWT Alpine Formula One Team",
    "Aston Martin Aramco Formula One Team",
    "Audi Revolut F1 Team",
    "Cadillac Formula",
    "Ferrari",
    "Haas F1 Team",
    "McLaren Mastercard",
    "Mercedes-AMG PETRONAS",
    "Visa Cash App Racing Bulls",
    "Oracle Red Bull Racing",
    "Atlassian Williams",
)
SPARK_2025_SEARCHES = (
    "C45",
    "A525",
    "FW47",
    "MCL39",
    "W16",
    "RB21",
    "VF-25",
    "VCARB 02",
    "AMR25",
)
STATE_FILE = Path(__file__).with_name("state.json")
CATALOG_FILE = Path(__file__).with_name("docs") / "catalog.json"
USER_AGENT = "sparkmodel-shop-change-monitor/1.0 (+GitHub Actions)"
_MINICHAMPS_OPENER = build_opener(HTTPCookieProcessor(CookieJar()))
_MINICHAMPS_LOCK = RLock()
_MINICHAMPS_SESSION_READY = False
_MINICHAMPS_MAX_RETRIES = 5
_MINICHAMPS_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
_REQUEST_MAX_RETRIES = 5
_REQUEST_RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}


def search_url(search):
    return f"{SEARCH_URL}?{urlencode({'search': search})}"


def spark_2025_url(search, page=1):
    filters = json.dumps(['year = "2025"'])
    params = {
        'q': search,
        'page_number': page,
        'page_size': 48,
        'filters': filters,
        'facets': '[]',
    }
    return f"{SPARK_API_URL}?{urlencode(params)}"


def minichamps_search_params(search, page=1):
    return {"p": page, "order": "score", "search": search}


def minichamps_url(search, page=1):
    return f"{MINICHAMPS_URL}?{urlencode(minichamps_search_params(search, page))}"


def minichamps_widget_url(search, page=1):
    return f"{MINICHAMPS_WIDGET_URL}?{urlencode({'search': search, 'p': page, 'order': 'score'})}"


SOURCE_URLS = (
    *(search_url(search) for search in TEAM_SEARCHES),
    *(f"{SPARK_SITE_URL}/collections?{urlencode({'q': search, 'pageSize': 48, 'year': 2025})}" for search in SPARK_2025_SEARCHES),
    LOOKSMART_SEARCH_URL,
    *(minichamps_url(search) for search in MINICHAMPS_SEARCHES),
)


def ferrari_match(name):
    name = name.lower()
    return "sf-26" in name or "scuderia ferrari hp" in name


def availability_label(value):
    return {
        "Available immediately": "Available",
        "Not available – pre-orders possible": "Pre-order",
    }.get(value, value)


def request(url, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json" if data else "text/html"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    for attempt in range(_REQUEST_MAX_RETRIES + 1):
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=45) as response:
                return response.read().decode(response.headers.get_content_charset() or "utf-8")
        except HTTPError as error:
            if error.code not in _REQUEST_RETRYABLE_HTTP_CODES or attempt >= _REQUEST_MAX_RETRIES:
                print(f"Request giving up after {attempt + 1} attempt(s): {url} ({error})", file=sys.stderr)
                raise
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            try:
                delay = min(float(retry_after), 60) if retry_after else min(2**attempt, 30)
            except ValueError:
                delay = min(2**attempt, 30)
        except (URLError, TimeoutError, UnicodeDecodeError, IncompleteRead, ConnectionError) as error:
            if attempt >= _REQUEST_MAX_RETRIES:
                raise RuntimeError(
                    f"Request failed after {_REQUEST_MAX_RETRIES + 1} attempts for {url}: {error}"
                ) from error
            delay = min(2**attempt, 30)

        print(
            f"Request failed ({error}); retry {attempt + 1}/{_REQUEST_MAX_RETRIES} "
            f"in {delay:g}s: {url}",
            file=sys.stderr,
        )
        time.sleep(delay)


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.box_depth = None
        self.current = None
        self.items = []
        self.delivery_depth = None
        self.delivery_text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div":
            self.div_depth += 1
            if self.current is None and "product-box" in attributes.get("class", ""):
                try:
                    self.current = json.loads(attributes["data-product-information"])
                except (KeyError, json.JSONDecodeError) as error:
                    raise RuntimeError("Unable to read product information") from error
                self.box_depth = self.div_depth
                self.delivery_depth = None
                self.delivery_text = []
        if self.current is None:
            return
        if tag == "a" and "product-name" in attributes.get("class", ""):
            self.current["url"] = attributes.get("href", "")
            self.current["name"] = attributes.get("title", self.current.get("name", ""))
        elif tag == "img" and "product-image" in attributes.get("class", ""):
            self.current["image_url"] = attributes.get("src", "")
        elif tag == "div" and "product-detail-delivery-information" in attributes.get("class", ""):
            self.delivery_depth = self.div_depth
            self.delivery_text = []

    def handle_data(self, data):
        if self.delivery_depth is not None:
            self.delivery_text.append(data)

    def handle_endtag(self, tag):
        if tag != "div":
            return
        if self.current is not None and self.delivery_depth == self.div_depth:
            self.current["availability"] = " ".join("".join(self.delivery_text).split())
            self.delivery_depth = None
        self.div_depth -= 1
        if self.current is not None and self.div_depth < self.box_depth:
            product_id = self.current.get("id")
            if not product_id or not self.current.get("url"):
                raise RuntimeError(f"Incomplete product card: {product_id}")
            item = {
                "name": self.current.get("name", ""),
                "url": self.current["url"],
            } | {"product_id": product_id}
            if self.current.get("image_url"):
                item["image_url"] = self.current["image_url"]
            if self.current.get("availability"):
                item["availability"] = self.current["availability"]
            self.items.append(item)
            self.current = None
            self.box_depth = None


class MinichampsListingParser(HTMLParser):
    """Parse Minichamps Shopware product cards and legacy WooCommerce cards."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.li_depth = 0
        self.card_depth = None
        self.current = None
        self.items = []
        self.next_url = ""
        self.capture_name = False
        self.name_parts = []
        self.shopware_card = None
        self.shopware_card_depth = None
        self.div_depth = 0
        self.current_page = 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = a.get("class", "").lower().split()
        href = a.get("href", "")
        if tag == "div":
            self.div_depth += 1
            if self.shopware_card is None and "product-box" in classes and a.get("data-product-information"):
                try:
                    data = json.loads(html_unescape(a["data-product-information"]))
                except (json.JSONDecodeError, TypeError):
                    data = {}
                self.shopware_card = {
                    "product_id": data.get("id", ""),
                    "name": data.get("name", ""),
                    "url": "",
                    "image_url": "",
                    "card_text": [],
                }
                self.shopware_card_depth = self.div_depth
        if self.shopware_card is not None:
            if tag == "a" and "product-name" in classes:
                self.shopware_card["url"] = href
                self.shopware_card["name"] = a.get("title") or self.shopware_card["name"]
            if tag == "img" and not self.shopware_card["image_url"]:
                image_url = a.get("data-src") or a.get("src") or a.get("data-lazy-src", "")
                if image_url and not re.search(r"dummy|placeholder|coming.?soon|sold.?out", image_url, re.I):
                    self.shopware_card["image_url"] = image_url
        if tag == "li":
            self.li_depth += 1
            if self.current is None and "product" in classes and "dealerliste" in classes:
                self.current = {"product_id": a.get("id", "").removeprefix("post-"), "status_classes": classes}
                self.card_depth = self.li_depth
                self.card_text = []
        if tag == "a":
            href_query = dict(parse_qsl(urlparse(href).query))
            try:
                linked_page = int(href_query.get("p", "0"))
            except ValueError:
                linked_page = 0
            is_next = "next" in classes or "page-numbers" in classes and a.get("aria-label", "").lower() == "next"
            if is_next:
                self.next_url = href
            elif linked_page > self.current_page:
                current_next = dict(parse_qsl(urlparse(self.next_url).query)).get("p", "")
                try:
                    current_next_page = int(current_next)
                except ValueError:
                    current_next_page = 0
                if not current_next_page or linked_page < current_next_page:
                    self.next_url = href
        if self.current is None:
            return
        if tag == "a" and a.get("href", "").find("/modelle/") >= 0 and not self.current.get("url"):
            self.current["url"] = a["href"]
        if tag == "div" and "background-image" in a.get("style", "") and not self.current.get("image_url"):
            match = re.search(r"background-image\s*:\s*url\(['\"]?(.*?)['\"]?\)", a["style"], re.I)
            if match:
                self.current["image_url"] = match.group(1)
        if tag == "h2" and "woocommerce-loop-product__title" in classes:
            self.capture_name = True
            self.name_parts = []

    def handle_data(self, data):
        if self.shopware_card is not None:
            self.shopware_card["card_text"].append(data)
        if self.current is not None:
            self.card_text.append(data)
        if getattr(self, "capture_name", False):
            self.name_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self.shopware_card_depth == self.div_depth:
            model = self.shopware_card
            text = " ".join(" ".join(model["card_text"]).split())
            if model.get("url") and model.get("name"):
                path_parts = [part for part in urlparse(model["url"]).path.split("/") if part]
                sku = path_parts[-1] if path_parts and re.fullmatch(r"\d{6,10}", path_parts[-1]) else ""
                if sku:
                    model["product_number"] = sku
                    model["product_id"] = sku
                else:
                    model["product_id"] = model["product_id"] or model["url"]
                model.update({"name": clean_minichamps_text(model["name"]), "source": "minichamps", "manufacturer": "Minichamps"})
                scale = re.search(r"\b1\s*[:/]\s*(\d+)\b", text)
                year = re.search(r"\b20\d{2}\b", model["name"] + " " + text)
                availability = re.search(r"\b(pre[- ]?order|in stock|available immediately|sold out|coming soon)\b", text, re.I)
                if scale: model["scale"] = f"1/{scale.group(1)}"
                if year: model["year"] = year.group(0)
                if availability:
                    label = availability.group(1).lower()
                    model["availability"] = "Pre-order" if "pre" in label else "Available" if label in {"in stock", "available immediately"} else "Sold out" if "sold" in label else "Coming soon"
                model.pop("card_text", None)
                self.items.append({key: value for key, value in model.items() if value})
            self.shopware_card = None
            self.shopware_card_depth = None
        if tag == "div":
            self.div_depth -= 1
        if tag == "h2" and self.capture_name:
            name = " ".join("".join(self.name_parts).split())
            if name:
                self.current["name"] = name
            self.capture_name = False
        if tag == "li":
            if self.current is not None and self.li_depth == self.card_depth:
                url = self.current.get("url", "")
                name = self.current.get("name", "")
                if url and name and self.current.get("product_id"):
                    text = " ".join(" ".join(self.card_text).split())
                    number = re.search(r"\b\d{6,10}\b", text)
                    scale = re.search(r"\b1\s*[:/]\s*(\d+)\b", text)
                    year = re.search(r"\b20\d{2}\b", text)
                    availability = re.search(r"This model is available on ([^.]+?)(?:\s+Delivery|$)", text, re.I)
                    self.current.update({"name": clean_minichamps_text(name), "url": url, "source": "minichamps", "manufacturer": "Minichamps"})
                    if number: self.current["product_number"] = number.group(0)
                    if scale: self.current["scale"] = f"1/{scale.group(1)}"
                    if year: self.current["year"] = year.group(0)
                    if "onbackorder" in self.current["status_classes"] or availability and "preorder" in availability.group(1).lower():
                        self.current["availability"] = "Pre-order"
                    elif "instock" in self.current["status_classes"]:
                        self.current["availability"] = "Available"
                    elif availability:
                        self.current["availability"] = availability.group(1).strip()
                    self.current.pop("status_classes", None)
                    self.items.append(self.current)
                self.current = None
                self.card_depth = None
            self.li_depth -= 1


class LooksmartListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.li_depth = 0
        self.div_depth = 0
        self.current = None
        self.items = []
        self.capture = None
        self.text = []
        self.next_url = ""

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        if tag == "div":
            self.div_depth += 1
        if tag == "li":
            self.li_depth += 1
            if self.current is None and "product" in classes and "type-product" in classes:
                post_class = next((value for value in classes if re.fullmatch(r"post-\d+", value)), "")
                self.current = {"product_id": post_class.removeprefix("post-")}
                self.current_depth = self.li_depth
        if tag == "a" and "next" in classes and "page-numbers" in classes:
            self.next_url = attributes.get("href", "")
        if self.current is None:
            return
        if tag == "a" and "woocommerce-loop-image-link" in classes:
            self.current["url"] = attributes.get("href", "")
        elif tag == "img" and "image_url" not in self.current:
            self.current["image_url"] = attributes.get("data-src") or attributes.get("src", "")
        elif tag == "h2" and "woocommerce-loop-product__title" in classes:
            self.capture = "name"
            self.text = []
        elif tag == "div" and "product-excerpt" in classes:
            self.capture = "excerpt"
            self.text = []
            self.excerpt_depth = self.div_depth
        elif tag == "br" and self.capture:
            self.text.append(" ")

    def handle_data(self, data):
        if self.capture:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "h2" and self.capture == "name":
            self.current["name"] = " ".join("".join(self.text).split())
            self.capture = None
        if tag == "div":
            if self.capture == "excerpt" and self.div_depth == self.excerpt_depth:
                text = " ".join("".join(self.text).split())
                self.current["excerpt"] = text
                self.capture = None
            self.div_depth -= 1
        if tag != "li":
            return
        self.li_depth -= 1
        if self.current is not None and self.li_depth < self.current_depth:
            if self.current.get("product_id") and self.current.get("url") and self.current.get("name"):
                self.items.append(self.current)
            self.current = None


def parse_looksmart_listing(html):
    parser = LooksmartListingParser()
    parser.feed(html)
    for item in parser.items:
        excerpt = item.pop("excerpt", "")
        code = re.search(r"Product\s+code\s*:\s*([\w-]+)", excerpt, re.I)
        availability = re.search(r"A(?:vailability|valiability)\s*:\s*(.+?)(?:\s+Quick View|$)", excerpt, re.I)
        scale = re.search(r"\b1[:/]\s*(5|8|12|18|43|64)\b", f"{item['name']} {excerpt}", re.I)
        item.update({
            "source": "looksmart",
            "year": "2025",
            "manufacturer": "Ferrari",
            "product_number": code.group(1) if code else "",
            "scale": f"1/{scale.group(1)}" if scale else "",
            "availability": availability.group(1).strip() if availability else "",
        })
    return parser.items, parser.next_url


def parse_listing(html):
    total_match = next((re.search(pattern, html, re.I) for pattern in (
        r"Showing\s+\d+\s+out\s+of\s+(\d+)\s+products",
        r"(\d+)\s+products\s+found\s+for",
        r"Showing\s+(\d+)\s+products",
    ) if re.search(pattern, html, re.I)), None)
    if total_match is None:
        raise RuntimeError("Unable to read product total from listing")
    parser = ListingParser()
    parser.feed(html)
    return parser.items, int(total_match.group(1))


def page_url(url, page):
    parts = urlsplit(url)
    query = parse_qsl(parts.query)
    found_page = False
    for index, (key, value) in enumerate(query):
        if key == "p":
            query[index] = (key, str(page))
            found_page = True
    if not found_page and page > 1:
        query.append(("p", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_search(search):
    products = {}
    total = None
    seen = 0
    for page in range(1, 1001):
        rows, page_total = parse_listing(request(page_url(search_url(search), page)))
        if total is None:
            total = page_total
        elif total != page_total:
            raise RuntimeError(f"Product total changed while fetching {search}")
        seen += len(rows)
        for row in rows:
            product_id = row.pop("product_id")
            if "2026" not in row["name"]:
                continue
            if search == "Ferrari" and not ferrari_match(row["name"]):
                continue
            products[product_id] = row
        if seen >= total:
            if seen != total:
                raise RuntimeError(f"Incomplete crawl for {search}: expected {total}, got {seen}")
            return products
        if not rows:
            raise RuntimeError(f"Empty page before {search} was complete")
    raise RuntimeError(f"Pagination exceeded 1000 pages for {search}")


def spark_availability(value):
    return {
        "CATALOGUE": "Catalogue",
        "INDEVELOPMENT": "In development",
        "COMINGSOON": "Coming soon",
        "LATESTMODELS": "Latest models",
    }.get(value, value or "")


def clean_product_name(value):
    return re.sub(r"^\s*cancel\s+", "", value or "", flags=re.I)


def clean_minichamps_text(value):
    return (value or "").replace("\ufffdC", "–").replace("\x96", "–").replace("\ufffd", "–").strip()


def fetch_spark_2025(search):
    products = {}
    total_pages = 1
    for page in range(1, 1001):
        payload = json.loads(request(spark_2025_url(search, page)))
        meta = payload.get("meta", {})
        total_pages = int(meta.get("total_pages") or 1)
        for product in payload.get("data", []):
            product_id = product.get("product_id")
            if not product_id:
                continue
            products[f"spark-2025-{product_id}"] = {
                "source": "sparkmodel",
                "source_id": product_id,
                "name": clean_product_name(product.get("name", "")),
                "url": f"{SPARK_SITE_URL}/products/{product_id}",
                "image_url": product.get("primary_image_url", ""),
                "availability": spark_availability(product.get("webcatalogue_state")),
                "product_number": product.get("code", ""),
                "scale": (product.get("scale_name") or "").replace(":", "/"),
                "year": str(product.get("year") or 2025),
                "manufacturer": product.get("manufacturer_name", ""),
            }
        if page >= total_pages:
            return products
    raise RuntimeError(f"Pagination exceeded 1000 pages for Spark {search}")


def fetch_looksmart():
    products = {}
    url = LOOKSMART_SEARCH_URL
    seen_pages = set()
    for _ in range(100):
        if url in seen_pages:
            raise RuntimeError("Looksmart pagination loop detected")
        seen_pages.add(url)
        rows, next_url = parse_looksmart_listing(request(url))
        for row in rows:
            product_id = row.pop("product_id")
            products[f"looksmart-{product_id}"] = row
        if not next_url:
            if not products:
                raise RuntimeError("Looksmart SF-25 search returned no products")
            return products
        resolved_url = urljoin(url, next_url)
        parsed_url = urlsplit(resolved_url)
        query = urlencode(parse_qsl(parsed_url.query, keep_blank_values=True))
        url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, query, parsed_url.fragment))
    raise RuntimeError("Looksmart pagination exceeded 100 pages")


def minichamps_request(url, *, ajax=False, referer=None):
    """Minichamps returns a same-path JS redirect on a new PHP session."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127 Safari/537.36", "Accept": "text/html,application/xhtml+xml"}
    if ajax:
        headers.update({"Accept": "text/html, */*;q=0.01", "X-Requested-With": "XMLHttpRequest", "Referer": referer or MINICHAMPS_URL})

    def initialize_session(reset=False):
        global _MINICHAMPS_OPENER, _MINICHAMPS_SESSION_READY
        with _MINICHAMPS_LOCK:
            if reset:
                _MINICHAMPS_OPENER = build_opener(HTTPCookieProcessor(CookieJar()))
                _MINICHAMPS_SESSION_READY = False
            if not _MINICHAMPS_SESSION_READY:
                with _MINICHAMPS_OPENER.open(Request(MINICHAMPS_BASE_URL, headers=headers), timeout=45) as response:
                    response.read()
                _MINICHAMPS_SESSION_READY = True

    for retry in range(_MINICHAMPS_MAX_RETRIES + 1):
        try:
            initialize_session()
            for session_attempt in range(2):
                with _MINICHAMPS_OPENER.open(Request(url, headers=headers), timeout=45) as response:
                    html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
                if len(html) > 1000 or not re.search(r"^\s*<script>\s*window\.location\.href=['\"]", html, re.I):
                    return html
                if session_attempt == 0:
                    initialize_session(reset=True)
            raise RuntimeError("Minichamps returned its PHP-session redirect instead of page HTML")
        except (HTTPError, URLError, TimeoutError, IncompleteRead) as error:
            if isinstance(error, HTTPError) and error.code not in _MINICHAMPS_RETRYABLE_HTTP_CODES:
                raise
            if retry >= _MINICHAMPS_MAX_RETRIES:
                raise
            delay = 2 ** retry
            initialize_session(reset=True)
            print(
                f"Minichamps request failed ({error}); retry {retry + 1}/{_MINICHAMPS_MAX_RETRIES} in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)

    raise AssertionError("unreachable")


def parse_minichamps_listing(html, page=1):
    parser = MinichampsListingParser()
    parser.current_page = page
    parser.feed(html)
    return parser.items, parser.next_url


def fetch_minichamps(search):
    products = {}
    seen = set()
    previous = load_state() or {}
    previous_ids_by_number = {
        item.get("product_number"): product_id
        for product_id, item in previous.items()
        if item.get("source") == "minichamps" and item.get("product_number")
    }
    for page in range(1, 101):
        url = minichamps_widget_url(search, page)
        if url in seen:
            raise RuntimeError(f"Minichamps pagination loop for {search}")
        seen.add(url)
        page_url = minichamps_url(search, page)
        rows, next_url = parse_minichamps_listing(minichamps_request(url, ajax=True, referer=page_url), page=page)
        for row in rows:
            product_id = row.pop("product_id")
            if not re.search(MINICHAMPS_MODEL_PATTERNS[search], row["name"], re.I):
                continue
            stable_id = previous_ids_by_number.get(row.get("product_number")) or f"minichamps-{product_id}"
            row["url"] = urljoin(MINICHAMPS_BASE_URL, row["url"])
            if row.get("image_url"):
                row["image_url"] = urljoin(MINICHAMPS_BASE_URL, row["image_url"])
            products[stable_id] = row
        if not next_url:
            if not products:
                raise RuntimeError(f"Minichamps {search} search returned no products")
            return products
    raise RuntimeError(f"Minichamps pagination exceeded 100 pages for {search}")


def fetch_all():
    products = {}
    for search in TEAM_SEARCHES:
        products.update(fetch_search(search))
    for search in SPARK_2025_SEARCHES:
        products.update(fetch_spark_2025(search))
    products.update(fetch_looksmart())
    if os.getenv("MINICHAMPS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}:
        for search in MINICHAMPS_SEARCHES:
            products.update(fetch_minichamps(search))
    else:
        # Keep the last known Minichamps snapshot while its site is unavailable,
        # so a temporary pause does not report every Minichamps product as removed.
        previous = load_state() or {}
        products.update({
            product_id: item
            for product_id, item in previous.items()
            if item.get("source") == "minichamps"
        })
        print("Minichamps monitoring is disabled; keeping its last known snapshot")
    return products


def load_state():
    if not STATE_FILE.exists():
        return None
    with STATE_FILE.open(encoding="utf-8") as file:
        state = json.load(file)
    return state.get("items")


def compare(old, new):
    old_ids, new_ids = set(old), set(new)
    added = [new[item_id] | {"product_id": item_id} for item_id in sorted(new_ids - old_ids)]
    removed = [old[item_id] | {"product_id": item_id} for item_id in sorted(old_ids - new_ids)]
    changed = []
    for item_id in sorted(old_ids & new_ids):
        changes = {
            field: (old[item_id].get(field, ""), new[item_id].get(field, ""))
            for field in ("image_url", "availability")
            if old[item_id].get(field, "") != new[item_id].get(field, "")
        }
        if changes:
            changed.append(new[item_id] | {"product_id": item_id, "changes": changes})
    return added, changed, removed


def catalog_metadata():
    if not CATALOG_FILE.exists():
        return {}
    with CATALOG_FILE.open(encoding="utf-8") as file:
        products = json.load(file).get("products", [])
    return {
        product["id"]: {
            "product_number": product.get("properties", {}).get("Product number", ""),
            "scale": product.get("properties", {}).get("Scale", ""),
        }
        for product in products
    }


def with_metadata(items, metadata, fetch_missing=False):
    result = []
    for item in items:
        details = metadata.get(item["product_id"]) or {
            "product_number": item.get("product_number", ""),
            "scale": item.get("scale", ""),
        }
        if not any(details.values()) and fetch_missing and item.get("source", "sparkmodelshop") == "sparkmodelshop":
            from catalog import parse_detail
            _, properties, _ = parse_detail(request(item["url"]))
            details = {
                "product_number": properties.get("Product number", ""),
                "scale": properties.get("Scale", ""),
            }
        result.append(item | (details or {}))
    return result


def line(item):
    name = " ".join(item["name"].split()).replace("[", "\\[").replace("]", "\\]")
    number = item.get("product_number") or "未获取"
    scale = item.get("scale") or "未获取"
    return f"- [{name}]({item['url']})（货号：{number}；比例：{scale}）"


def changed_line(item):
    labels = []
    if "image_url" in item["changes"]:
        labels.append("封面图片已更新")
    if "availability" in item["changes"]:
        old, new = item["changes"]["availability"]
        labels.append(f"Availability：{availability_label(old) or '—'} → {availability_label(new) or '—'}")
    return f"{line(item)}（{'；'.join(labels)}）"


def build_message(total, added, changed, removed, initial=False):
    keyword = os.getenv("DINGTALK_KEYWORD") or "成绩"
    if initial:
        return f"### {keyword} Spark Model Shop 监控已启动\n\n已记录 Formula 1 商品，共 **{total}** 件。"
    cover_changes = sum("image_url" in item["changes"] for item in changed)
    availability_changes = sum("availability" in item["changes"] for item in changed)
    sections = [
        f"### {keyword} Spark Model Shop 变化提醒",
        f"Formula 1 当前 **{total}** 件；新增 **{len(added)}**，封面变化 **{cover_changes}**，Availability 变化 **{availability_changes}**，下架 **{len(removed)}**。",
    ]
    for title, items, formatter in (("新增", added, line), ("字段变化", changed, changed_line), ("下架", removed, line)):
        if items:
            sections.extend((f"#### {title}", *map(formatter, items[:20])))
            if len(items) > 20:
                sections.append(f"- 另有 {len(items) - 20} 件未展开")
    return "\n\n".join(sections)


def send_dingtalk(markdown):
    webhook = os.getenv("DINGTALK_WEBHOOK", "").strip()
    if not webhook:
        raise RuntimeError("DINGTALK_WEBHOOK is not configured")
    parsed = urlparse(webhook)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith("dingtalk.com"):
        raise RuntimeError("DINGTALK_WEBHOOK must be an HTTPS dingtalk.com URL")
    result = json.loads(request(webhook, {
        "msgtype": "markdown",
        "markdown": {"title": "Spark Model Shop 变化提醒", "text": markdown},
    }))
    if result.get("errcode") != 0:
        raise RuntimeError(f"DingTalk rejected message: {result}")


def save_state(items, added=(), changed=(), removed=()):
    state = {
        "sources": list(SOURCE_URLS),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(items),
        "items": dict(sorted(items.items())),
        "changes": {
            "added": sorted(added),
            "changed": sorted(changed),
            "removed": sorted(removed),
        },
    }
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    current = fetch_all()
    previous = load_state()
    if previous is None:
        send_dingtalk(build_message(len(current), [], [], [], initial=True))
        save_state(current, added=current)
        print(f"Initialized with {len(current)} products")
        return True
    added, changed, removed = compare(previous, current)
    if not any((added, changed, removed)):
        print(f"No change ({len(current)} products)")
        return False
    metadata = catalog_metadata()
    added = with_metadata(added, metadata, fetch_missing=True)
    changed = with_metadata(changed, metadata, fetch_missing=True)
    removed = with_metadata(removed, metadata)
    send_dingtalk(build_message(len(current), added, changed, removed))
    save_state(
        current,
        added=(item["product_id"] for item in added),
        changed=(item["product_id"] for item in changed),
        removed=(item["product_id"] for item in removed),
    )
    print(f"Changed: +{len(added)} fields={len(changed)} -{len(removed)}")
    return True


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
