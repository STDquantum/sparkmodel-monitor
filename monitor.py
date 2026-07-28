#!/usr/bin/env python3
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

SEARCH_URL = "https://www.sparkmodelshop.com/de/en/search"
SEARCH_PROPERTY = "881036a7528b682be67aa6e2c171e1de"
TEAM_SEARCHES = (
    "BWT Alpine Formula One Team",
    "Aston Martin Aramco Formula One Team",
    "Audi Revolut F1 Team",
    "Cadillac Formula 1 Team",
    "Ferrari",
    "Haas F1 Team",
    "McLaren Mastercard",
    "Mercedes-AMG PETRONAS",
    "Visa Cash App Racing Bulls",
    "Oracle Red Bull Racing",
    "Atlassian Williams",
)
STATE_FILE = Path(__file__).with_name("state.json")
CATALOG_FILE = Path(__file__).with_name("docs") / "catalog.json"
USER_AGENT = "sparkmodel-shop-change-monitor/1.0 (+GitHub Actions)"


def search_url(search):
    return f"{SEARCH_URL}?{urlencode({'properties': SEARCH_PROPERTY, 'p': 1, 'order': 'score', 'search': search})}"


SOURCE_URLS = tuple(search_url(search) for search in TEAM_SEARCHES)


def ferrari_match(name):
    name = name.lower()
    return "sf-26" in name or "scuderia ferrari hp" in name


def request(url, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json" if data else "text/html"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=45) as response:
                return response.read().decode(response.headers.get_content_charset() or "utf-8")
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.box_depth = None
        self.current = None
        self.items = []

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
        if self.current is None:
            return
        if tag == "a" and "product-name" in attributes.get("class", ""):
            self.current["url"] = attributes.get("href", "")
            self.current["name"] = attributes.get("title", self.current.get("name", ""))
        elif tag == "img" and "product-image" in attributes.get("class", ""):
            self.current["image_url"] = attributes.get("src", "")

    def handle_endtag(self, tag):
        if tag != "div":
            return
        self.div_depth -= 1
        if self.current is not None and self.div_depth < self.box_depth:
            product_id = self.current.get("id")
            if not product_id or not self.current.get("url") or not self.current.get("image_url"):
                raise RuntimeError(f"Incomplete product card: {product_id}")
            self.items.append({
                "name": self.current.get("name", ""),
                "url": self.current["url"],
                "image_url": self.current["image_url"],
            } | {"product_id": product_id})
            self.current = None
            self.box_depth = None


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
    query = [(key, str(page) if key == "p" else value) for key, value in parse_qsl(parts.query)]
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
            if search != "Ferrari" or ferrari_match(row["name"]):
                products[product_id] = row
        if seen >= total:
            if seen != total:
                raise RuntimeError(f"Incomplete crawl for {search}: expected {total}, got {seen}")
            return products
        if not rows:
            raise RuntimeError(f"Empty page before {search} was complete")
    raise RuntimeError(f"Pagination exceeded 1000 pages for {search}")


def fetch_all():
    products = {}
    for search in TEAM_SEARCHES:
        products.update(fetch_search(search))
    return products


def load_state():
    if not STATE_FILE.exists():
        return None
    with STATE_FILE.open(encoding="utf-8") as file:
        state = json.load(file)
    return state.get("items") if state.get("sources") == list(SOURCE_URLS) else None


def compare(old, new):
    old_ids, new_ids = set(old), set(new)
    added = [new[item_id] | {"product_id": item_id} for item_id in sorted(new_ids - old_ids)]
    removed = [old[item_id] | {"product_id": item_id} for item_id in sorted(old_ids - new_ids)]
    changed = [
        new[item_id] | {"product_id": item_id}
        for item_id in sorted(old_ids & new_ids)
        if old[item_id].get("image_url") != new[item_id].get("image_url")
    ]
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
        details = metadata.get(item["product_id"])
        if details is None and fetch_missing:
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


def build_message(total, added, changed, removed, initial=False):
    keyword = os.getenv("DINGTALK_KEYWORD") or "成绩"
    if initial:
        return f"### {keyword} Spark Model Shop 监控已启动\n\n已记录 Formula 1 商品，共 **{total}** 件。"
    sections = [
        f"### {keyword} Spark Model Shop 变化提醒",
        f"Formula 1 当前 **{total}** 件；新增 **{len(added)}**，封面变化 **{len(changed)}**，下架 **{len(removed)}**。",
    ]
    for title, items in (("新增", added), ("封面变化", changed), ("下架", removed)):
        if items:
            sections.extend((f"#### {title}", *map(line, items[:20])))
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
    print(f"Changed: +{len(added)} cover={len(changed)} -{len(removed)}")
    return True


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
