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

SPARK_API_URL = "https://rapi.sparkmodel.com/products"
SPARK_SITE_URL = "https://www.sparkmodel.com"
LOOKSMART_SEARCHES = ("SF-25", "SF-26")
MINICHAMPS_BASE_URL = "https://www.minichamps.de/"
MINICHAMPS_URL = "https://www.minichamps.de/en/search"
MINICHAMPS_WIDGET_URL = "https://www.minichamps.de/en/widgets/search"
MINICHAMPS_2025_PROPERTIES = "019a86b46f8b7431bab8f63c093a3507"
MINICHAMPS_SEARCHES = ("W17", "VF-26", "AMR26", "VCARB 03", "MAC-26", "A526", "Audi R26", "RB22", "FW48", "MCL40")
MINICHAMPS_MODEL_PATTERNS = {
    "W17": r"\bW17\b", "VF-26": r"\bVF-26\b", "AMR26": r"\bAMR26\b",
    "VCARB 03": r"\bVCARB\s*03\b", "MAC-26": r"\bMAC-26\b", "A526": r"\bA526\b",
    "Audi R26": r"\bR26\b", "RB22": r"\bRB22\b", "FW48": r"\bFW48\b", "MCL40": r"\bMCL40\b",
}
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
SPARK_2026_SEARCHES = (
    "VF26",
    "MAC26",
    "FW48",
    "AMR26",
    "A526",
    "W17",
    "R26",
    "MCL40",
    "VCARB03",
    "RB22",
)
STATE_FILE = Path(__file__).with_name("state.json")
CATALOG_FILE = Path(__file__).with_name("docs") / "catalog.json"
USER_AGENT = "sparkmodel-monitor/1.0 (+GitHub Actions)"
_MINICHAMPS_OPENER = build_opener(HTTPCookieProcessor(CookieJar()))
_MINICHAMPS_LOCK = RLock()
_MINICHAMPS_SESSION_READY = False
_MINICHAMPS_MAX_ATTEMPTS = 5
_SOURCE_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.8037.98 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.4258.53",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.8037.98 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.8037.97 Safari/537.36 Edg/154.0.4258.53",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.8037.97 Safari/537.36",
)
_MINICHAMPS_RETRYABLE_HTTP_CODES = {403, 429, 500, 502, 503, 504}
_REQUEST_MAX_RETRIES = 5
_REQUEST_RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}
_SOURCE_MAX_ATTEMPTS = 5
_SOURCE_RETRYABLE_HTTP_CODES = _REQUEST_RETRYABLE_HTTP_CODES | {403}


def spark_url(search, page=1, year=None):
    params = {
        'q': search,
        'page_number': page,
        'page_size': 48,
    }
    if year is not None:
        params['filters'] = json.dumps([f'year = "{year}"'])
        params['facets'] = '[]'
    return f"{SPARK_API_URL}?{urlencode(params)}"


def spark_2025_url(search, page=1):
    return spark_url(search, page, year=2025)


def spark_collection_url(search):
    return f"{SPARK_SITE_URL}/collections?{urlencode({'q': search, 'pageSize': 48})}"


def looksmart_search_url(search):
    return f"https://looksmartmodels.com/?{urlencode({'s': search, 'post_type': 'product', 'dgwt_wcas': 1})}"


def minichamps_search_params(search, page=1):
    return {"p": page, "order": "score", "search": search}


def minichamps_url(search, page=1):
    return f"{MINICHAMPS_URL}?{urlencode(minichamps_search_params(search, page))}"


def minichamps_widget_url(search, page=1):
    return f"{MINICHAMPS_WIDGET_URL}?{urlencode({'search': search, 'p': page, 'order': 'score'})}"


def minichamps_2025_url(page=1):
    return f"{MINICHAMPS_BASE_URL}en/Formula-1/?{urlencode({'properties': MINICHAMPS_2025_PROPERTIES, 'p': page, 'order': 'name-asc'})}"


SOURCE_URLS = (
    *(f"{SPARK_SITE_URL}/collections?{urlencode({'q': search, 'pageSize': 48, 'year': 2025})}" for search in SPARK_2025_SEARCHES),
    *(spark_collection_url(search) for search in SPARK_2026_SEARCHES),
    *(looksmart_search_url(search) for search in LOOKSMART_SEARCHES),
    *(minichamps_url(search) for search in MINICHAMPS_SEARCHES),
    minichamps_2025_url(),
)


def availability_label(value):
    return {
        "Available immediately": "Available",
        "Not available – pre-orders possible": "Pre-order",
    }.get(value, value)


def request(url, payload=None, *, source_request=False, referer=None, accept=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    if data is not None:
        content_type = "application/json; charset=utf-8"
    else:
        content_type = None
    max_attempts = _SOURCE_MAX_ATTEMPTS if source_request else _REQUEST_MAX_RETRIES + 1
    retryable_http_codes = _SOURCE_RETRYABLE_HTTP_CODES if source_request else _REQUEST_RETRYABLE_HTTP_CODES
    for attempt in range(1, max_attempts + 1):
        failure = None
        headers = {
            "User-Agent": _SOURCE_USER_AGENTS[(attempt - 1) % len(_SOURCE_USER_AGENTS)] if source_request else USER_AGENT,
            "Accept": accept or ("application/json" if data else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        }
        if source_request:
            headers["Accept-Language"] = "en-GB,en;q=0.9,de;q=0.8"
            if referer:
                headers["Referer"] = referer
        if content_type:
            headers["Content-Type"] = content_type
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=45) as response:
                return response.read().decode(response.headers.get_content_charset() or "utf-8")
        except HTTPError as error:
            failure = error
            if error.code not in retryable_http_codes or attempt >= max_attempts:
                print(f"Request giving up after {attempt} attempt(s): {url} ({error})", file=sys.stderr)
                raise
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            try:
                delay = min(float(retry_after), 60) if retry_after else min(2 ** (attempt - 1), 30)
            except ValueError:
                delay = min(2 ** (attempt - 1), 30)
        except (URLError, TimeoutError, UnicodeDecodeError, IncompleteRead, ConnectionError) as error:
            failure = error
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"Request failed after {attempt} attempts for {url}: {error}"
                ) from error
            delay = min(2 ** (attempt - 1), 30)

        print(
            f"Request failed ({failure}); next attempt {attempt + 1}/{max_attempts} "
            f"in {delay:g}s{'; rotating User-Agent' if source_request else ''}: {url}",
            file=sys.stderr,
        )
        time.sleep(delay)


class MinichampsListingParser(HTMLParser):
    """Parse Minichamps Shopware product cards."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.next_url = ""
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

    def handle_data(self, data):
        if self.shopware_card is not None:
            self.shopware_card["card_text"].append(data)

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


def spark_availability(value):
    return {
        "CATALOGUE": "Catalogue",
        "INDEVELOPMENT": "In development",
        "COMINGSOON": "Coming soon",
        "LATESTMODELS": "Latest models",
    }.get(value, value or "")


def clean_product_name(value):
    return re.sub(r"^\s*cancel\s+", "", value or "", flags=re.I)


def title_has_2026(name):
    return bool(re.search(r"\b2026\b", name or ""))


def is_scale_1_5(scale, name=""):
    return bool(re.search(r"\b1\s*[:/]\s*5\b", f"{scale or ''} {name or ''}", re.I))


def clean_minichamps_text(value):
    return (value or "").replace("\ufffdC", "–").replace("\x96", "–").replace("\ufffd", "–").strip()


def normalized_model_code(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def fetch_spark_2025(search):
    products = {}
    total_pages = 1
    for page in range(1, 1001):
        payload = json.loads(request(
            spark_2025_url(search, page),
            source_request=True,
            referer=spark_collection_url(search),
            accept="application/json",
        ))
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


def fetch_spark_2026(search):
    products = {}
    total_pages = 1
    for page in range(1, 1001):
        payload = json.loads(request(
            spark_url(search, page),
            source_request=True,
            referer=spark_collection_url(search),
            accept="application/json",
        ))
        meta = payload.get("meta", {})
        total_pages = int(meta.get("total_pages") or 1)
        for product in payload.get("data", []):
            product_id = product.get("product_id")
            if not product_id:
                continue
            name = clean_product_name(product.get("name", ""))
            scale = (product.get("scale_name") or "").replace(":", "/")
            if not title_has_2026(name) or is_scale_1_5(scale, name):
                continue
            products[f"spark-2026-{product_id}"] = {
                "source": "sparkmodel",
                "source_id": product_id,
                "name": name,
                "url": f"{SPARK_SITE_URL}/products/{product_id}",
                "image_url": product.get("primary_image_url", ""),
                "availability": spark_availability(product.get("webcatalogue_state")),
                "product_number": product.get("code", ""),
                "scale": scale,
                "year": "2026",
                "manufacturer": product.get("manufacturer_name", ""),
            }
        if page >= total_pages:
            return products
    raise RuntimeError(f"Pagination exceeded 1000 pages for Spark {search}")


def fetch_looksmart(search):
    products = {}
    url = looksmart_search_url(search)
    referer = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"
    seen_pages = set()
    for _ in range(100):
        if url in seen_pages:
            raise RuntimeError("Looksmart pagination loop detected")
        seen_pages.add(url)
        rows, next_url = parse_looksmart_listing(request(url, source_request=True, referer=referer))
        for row in rows:
            product_id = row.pop("product_id")
            if search == "SF-26":
                if not title_has_2026(row.get("name", "")):
                    continue
                if is_scale_1_5(row.get("scale"), row.get("name")):
                    continue
                row["year"] = "2026"
            products[f"looksmart-{product_id}"] = row
        if not next_url:
            if not products:
                qualifier = "matching " if search == "SF-26" else ""
                raise RuntimeError(f"Looksmart {search} search returned no {qualifier}products")
            return products
        resolved_url = urljoin(url, next_url)
        parsed_url = urlsplit(resolved_url)
        query = urlencode(parse_qsl(parsed_url.query, keep_blank_values=True))
        referer = url
        url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, query, parsed_url.fragment))
    raise RuntimeError("Looksmart pagination exceeded 100 pages")


def minichamps_request(url, *, ajax=False, referer=None):
    """Minichamps returns a same-path JS redirect on a new PHP session."""
    def request_headers(attempt):
        headers = {
            "User-Agent": _SOURCE_USER_AGENTS[(attempt - 1) % len(_SOURCE_USER_AGENTS)],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9,de;q=0.8",
        }
        if ajax:
            headers.update({
                "Accept": "text/html, */*;q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": referer or MINICHAMPS_URL,
            })
        return headers

    def reset_session():
        global _MINICHAMPS_OPENER, _MINICHAMPS_SESSION_READY
        with _MINICHAMPS_LOCK:
            _MINICHAMPS_OPENER = build_opener(HTTPCookieProcessor(CookieJar()))
            _MINICHAMPS_SESSION_READY = False

    def initialize_session(headers):
        global _MINICHAMPS_SESSION_READY
        with _MINICHAMPS_LOCK:
            if not _MINICHAMPS_SESSION_READY:
                with _MINICHAMPS_OPENER.open(Request(MINICHAMPS_BASE_URL, headers=headers), timeout=45) as response:
                    response.read()
                _MINICHAMPS_SESSION_READY = True

    for attempt in range(1, _MINICHAMPS_MAX_ATTEMPTS + 1):
        headers = request_headers(attempt)
        try:
            initialize_session(headers)
            for session_attempt in range(2):
                with _MINICHAMPS_OPENER.open(Request(url, headers=headers), timeout=45) as response:
                    html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
                if len(html) > 1000 or not re.search(r"^\s*<script>\s*window\.location\.href=['\"]", html, re.I):
                    return html
                if session_attempt == 0:
                    reset_session()
                    initialize_session(headers)
            raise RuntimeError("Minichamps returned its PHP-session redirect instead of page HTML")
        except (HTTPError, URLError, TimeoutError, IncompleteRead) as error:
            if isinstance(error, HTTPError) and error.code not in _MINICHAMPS_RETRYABLE_HTTP_CODES:
                raise
            if attempt >= _MINICHAMPS_MAX_ATTEMPTS:
                raise
            delay = 2 ** (attempt - 1)
            reset_session()
            print(
                f"Minichamps request failed ({error}); next attempt {attempt + 1}/{_MINICHAMPS_MAX_ATTEMPTS} "
                f"in {delay}s with a different User-Agent",
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


def fetch_minichamps_2025():
    products = {}
    seen = set()
    previous = load_state() or {}
    previous_ids_by_number = {
        item.get("product_number"): product_id
        for product_id, item in previous.items()
        if item.get("source") == "minichamps" and item.get("product_number")
    }
    url = minichamps_2025_url()
    for page in range(1, 101):
        if url in seen:
            raise RuntimeError("Minichamps 2025 pagination loop detected")
        seen.add(url)
        html = minichamps_request(url, referer=minichamps_2025_url())
        rows, next_url = parse_minichamps_listing(html, page=page)
        for row in rows:
            product_id = row.pop("product_id")
            row["year"] = row.get("year") or "2025"
            stable_id = previous_ids_by_number.get(row.get("product_number")) or f"minichamps-{product_id}"
            row["url"] = urljoin(MINICHAMPS_BASE_URL, row["url"])
            if row.get("image_url"):
                row["image_url"] = urljoin(MINICHAMPS_BASE_URL, row["image_url"])
            products[stable_id] = row
        if not next_url:
            if not products:
                raise RuntimeError("Minichamps 2025 category returned no products")
            return products
        # Shopware's generated pager can drop the selected property filter.
        # Rebuild every page URL so the 2025 constraint is always retained.
        url = minichamps_2025_url(page + 1)
    raise RuntimeError("Minichamps 2025 pagination exceeded 100 pages")


def fetch_all():
    products = {}
    previous = load_state() or {}
    failed_crawls = set()

    def fetch_and_merge(label, source, crawl_key, fetcher, *args):
        print(f"[{datetime.now().astimezone():%H:%M:%S}] Fetching {label}", flush=True)
        try:
            batch = fetcher(*args)
        except Exception as error:
            failed_crawls.add((source, crawl_key))
            print(
                f"Skipped this crawl for {label}; other crawls will continue and "
                f"previous matching products will be kept ({error})",
                flush=True,
            )
            return
        products.update(batch)
        print(
            f"[{datetime.now().astimezone():%H:%M:%S}] Finished {label}: "
            f"{len(batch)} products; {len(products)} unique total",
            flush=True,
        )

    for search in SPARK_2025_SEARCHES:
        fetch_and_merge(f"Spark 2025 · {search}", "sparkmodel", ("spark2025", search), fetch_spark_2025, search)
    for search in SPARK_2026_SEARCHES:
        fetch_and_merge(f"Spark 2026 · {search}", "sparkmodel", ("spark2026", search), fetch_spark_2026, search)
    for search in LOOKSMART_SEARCHES:
        fetch_and_merge(f"Looksmart · {search}", "looksmart", ("looksmart", search), fetch_looksmart, search)
    if os.getenv("MINICHAMPS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}:
        for search in MINICHAMPS_SEARCHES:
            fetch_and_merge(
                f"Minichamps 2026 · {search}",
                "minichamps",
                ("minichamps2026", search),
                fetch_minichamps,
                search,
            )
        fetch_and_merge(
            "Minichamps 2025 category",
            "minichamps",
            ("minichamps2025", "category"),
            fetch_minichamps_2025,
        )
    else:
        # Keep the last known Minichamps snapshot while its site is unavailable,
        # so a temporary pause does not report every Minichamps product as removed.
        products.update({
            product_id: item
            for product_id, item in previous.items()
            if item.get("source") == "minichamps"
        })
        print("Minichamps monitoring is disabled; keeping its last known snapshot")

    def matches_crawl(item, crawl_key):
        crawl_type, search = crawl_key
        name = item.get("name", "")
        if crawl_type == "spark2025":
            return item.get("source") == "sparkmodel" and normalized_model_code(search) in normalized_model_code(name)
        if crawl_type == "spark2026":
            return (
                item.get("source") == "sparkmodel"
                and str(item.get("year", "")) == "2026"
                and normalized_model_code(search) in normalized_model_code(name)
            )
        if crawl_type == "looksmart":
            return item.get("source") == "looksmart" and normalized_model_code(search) in normalized_model_code(name)
        if crawl_type == "minichamps2026":
            return (
                item.get("source") == "minichamps"
                and str(item.get("year", "")) == "2026"
                and bool(re.search(MINICHAMPS_MODEL_PATTERNS[search], name, re.I))
            )
        if crawl_type == "minichamps2025":
            return item.get("source") == "minichamps" and str(item.get("year", "")) == "2025"
        return False

    # A failed keyword keeps its matching old products. Successful keywords,
    # including later queries from the same provider, still use fresh results.
    for product_id, item in previous.items():
        if any(
            item.get("source") == source and matches_crawl(item, crawl_key)
            for source, crawl_key in failed_crawls
        ):
            products.setdefault(product_id, item)

    print(f"[{datetime.now().astimezone():%H:%M:%S}] Fetch complete: {len(products)} unique products", flush=True)
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
    for index, item in enumerate(items):
        details = metadata.get(item["product_id"]) or {
            "product_number": item.get("product_number", ""),
            "scale": item.get("scale", ""),
        }
        if fetch_missing and index < 20 and (not details.get("product_number") or not details.get("scale")):
            source = item.get("source", "sparkmodel")
            try:
                if source == "minichamps":
                    from catalog import parse_minichamps_detail
                    _, properties, _ = parse_minichamps_detail(minichamps_request(item["url"]))
                elif source == "sparkmodel":
                    source_id = item.get("source_id") or item["product_id"].removeprefix("spark-2026-").removeprefix("spark-2025-")
                    detail = json.loads(request(
                        f"{SPARK_API_URL}/{source_id}",
                        source_request=True,
                        referer=item.get("url") or SPARK_SITE_URL,
                        accept="application/json",
                    ))
                    properties = {
                        "Product number": detail.get("code", ""),
                        "Scale": detail.get("scale", {}).get("name", ""),
                    }
                else:
                    properties = {}
            except Exception as error:
                print(f"Optional detail lookup skipped for {item['product_id']}; keeping listing data ({error})", flush=True)
                properties = {}
            details = {
                "product_number": details.get("product_number") or item.get("product_number") or properties.get("Product number", ""),
                "scale": details.get("scale") or item.get("scale") or properties.get("Scale", ""),
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
        return f"### {keyword} Spark Model 监控已启动\n\n已记录 Formula 1 商品，共 **{total}** 件。"
    cover_changes = sum("image_url" in item["changes"] for item in changed)
    availability_changes = sum("availability" in item["changes"] for item in changed)
    sections = [
        f"### {keyword} Spark Model 变化提醒",
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
        "markdown": {"title": "Spark Model 变化提醒", "text": markdown},
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
    print(f"[{datetime.now().astimezone():%H:%M:%S}] Starting product monitoring", flush=True)
    current = fetch_all()
    previous = load_state()
    if previous is None:
        print("No previous snapshot; sending initial monitoring message", flush=True)
        send_dingtalk(build_message(len(current), [], [], [], initial=True))
        save_state(current, added=current)
        print(f"Initialized with {len(current)} products")
        return True
    print(f"Comparing snapshots: previous={len(previous)}, current={len(current)}", flush=True)
    added, changed, removed = compare(previous, current)
    print(f"Detected changes: added={len(added)}, changed={len(changed)}, removed={len(removed)}", flush=True)
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
