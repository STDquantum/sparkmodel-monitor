#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API_URL = "https://rapi.sparkmodel.com/products"
CATEGORY_ID = "4d9b8ce5-f8a2-4bb2-a713-a16aae6d8da2"
YEAR = "2026"
PAGE_SIZE = 48
STATE_FILE = Path(__file__).with_name("state.json")
USER_AGENT = "sparkmodel-change-monitor/1.0 (+GitHub Actions)"


def request_json(url, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=45) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def fetch_all():
    filters = [f'category_ids = "{CATEGORY_ID}"', f'year = "{YEAR}"']
    products = {}
    page = 1
    total = None
    while page <= 1000:
        query = urlencode({
            "q": "",
            "page_number": page,
            "page_size": PAGE_SIZE,
            "filters": json.dumps(filters),
            "facets": "[]",
        })
        response = request_json(f"{API_URL}?{query}")
        rows = response.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("Spark API response has no data list")
        total = max(total or 0, int(response.get("meta", {}).get("total_hits", 0)))
        for row in rows:
            product_id = row.get("product_id")
            if not product_id:
                raise RuntimeError("Spark API returned a product without product_id")
            products[product_id] = {
                "code": row.get("code") or "",
                "name": row.get("name") or "",
                "photo_id": row.get("photo_id"),
                "primary_image_url": row.get("primary_image_url"),
            }
        if not rows or (len(rows) < PAGE_SIZE and len(products) >= total):
            break
        page += 1
    else:
        raise RuntimeError("Pagination exceeded 1000 pages")
    if total is None or len(products) != total:
        raise RuntimeError(f"Incomplete crawl: expected {total}, got {len(products)}")
    return products


def load_state():
    if not STATE_FILE.exists():
        return None
    with STATE_FILE.open(encoding="utf-8") as file:
        state = json.load(file)
    return state.get("items", {})


def compare(old, new):
    old_ids, new_ids = set(old), set(new)
    added = [new[item_id] | {"product_id": item_id} for item_id in sorted(new_ids - old_ids)]
    removed = [old[item_id] | {"product_id": item_id} for item_id in sorted(old_ids - new_ids)]
    changed = []
    for item_id in sorted(old_ids & new_ids):
        before, after = old[item_id], new[item_id]
        if (before.get("photo_id"), before.get("primary_image_url")) != (
            after.get("photo_id"), after.get("primary_image_url")
        ):
            changed.append(after | {"product_id": item_id})
    return added, changed, removed


def line(item):
    name = " ".join(item["name"].split())
    url = f"https://www.sparkmodel.com/products/{item['product_id']}"
    return f"- [{item['code']} {name}]({url})"


def build_message(total, added, changed, removed, initial=False):
    keyword = os.getenv("DINGTALK_KEYWORD") or "Spark模型"
    if initial:
        return f"### {keyword}监控已启动\n\n已记录 {YEAR} 年筛选结果，共 **{total}** 条。"
    sections = [
        f"### {keyword}网页变化提醒",
        f"当前 **{total}** 条；新增 **{len(added)}**，封面变化 **{len(changed)}**，下架 **{len(removed)}**。",
    ]
    for title, items in (("新增", added), ("封面变化", changed), ("下架", removed)):
        if items:
            sections.extend((f"#### {title}", *map(line, items[:20])))
            if len(items) > 20:
                sections.append(f"- 另有 {len(items) - 20} 条未展开")
    return "\n\n".join(sections)


def send_dingtalk(markdown):
    webhook = os.getenv("DINGTALK_WEBHOOK", "").strip()
    if not webhook:
        raise RuntimeError("DINGTALK_WEBHOOK is not configured")
    parsed = urlparse(webhook)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith("dingtalk.com"):
        raise RuntimeError("DINGTALK_WEBHOOK must be an HTTPS dingtalk.com URL")
    result = request_json(webhook, {
        "msgtype": "markdown",
        "markdown": {"title": "Spark模型网页变化提醒", "text": markdown},
    })
    if result.get("errcode") != 0:
        raise RuntimeError(f"DingTalk rejected message: {result}")


def save_state(items):
    state = {
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
