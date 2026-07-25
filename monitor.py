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

LISTING_URL = (
    "https://www.sparkmodelshop.com/de/en/models/formula/formula-1/"
    "?properties=881036a7528b682be67aa6e2c171e1de&p=1&order=release-date-desc"
)
STATE_FILE = Path(__file__).with_name("state.json")
USER_AGENT = "sparkmodel-shop-change-monitor/1.0 (+GitHub Actions)"


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
    total_match = re.search(r"Showing\s+\d+\s+out\s+of\s+(\d+)\s+products", html)
    if not total_match:
        raise RuntimeError("Unable to read product total from listing")
    parser = ListingParser()
    parser.feed(html)
    return parser.items, int(total_match.group(1))


def page_url(page):
    parts = urlsplit(LISTING_URL)
    query = [(key, str(page) if key == "p" else value) for key, value in parse_qsl(parts.query)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_all():
    products = {}
    total = None
    page = 1
    while page <= 1000:
        rows, page_total = parse_listing(request(page_url(page)))
        total = max(total or 0, page_total)
        for row in rows:
            product_id = row.pop("product_id")
            products[product_id] = row
        if len(products) >= total:
            break
        if not rows:
            raise RuntimeError("Empty page before the listing was complete")
        page += 1
    else:
        raise RuntimeError("Pagination exceeded 1000 pages")
    if len(products) != total:
        raise RuntimeError(f"Incomplete crawl: expected {total}, got {len(products)}")
    return products


def load_state():
    if not STATE_FILE.exists():
        return None
    with STATE_FILE.open(encoding="utf-8") as file:
        state = json.load(file)
    return state.get("items") if state.get("source") == LISTING_URL else None


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


def line(item):
    name = " ".join(item["name"].split()).replace("[", "\\[").replace("]", "\\]")
    return f"- [{name}]({item['url']})"


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


def save_state(items):
    state = {
        "source": LISTING_URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(items),
        "items": dict(sorted(items.items())),
    }
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    current = fetch_all()
    previous = load_state()
    if previous is None:
        send_dingtalk(build_message(len(current), [], [], [], initial=True))
        save_state(current)
        print(f"Initialized with {len(current)} products")
        return
    added, changed, removed = compare(previous, current)
    if not any((added, changed, removed)):
        print(f"No change ({len(current)} products)")
        return
    send_dingtalk(build_message(len(current), added, changed, removed))
    save_state(current)
    print(f"Changed: +{len(added)} cover={len(changed)} -{len(removed)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
