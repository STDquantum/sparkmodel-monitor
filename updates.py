#!/usr/bin/env python3
"""Compare the new catalogue with the last committed snapshot and publish updates."""

import hashlib
import json
import subprocess
import argparse
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
CATALOG = DOCS / "catalog.json"
REPORT = DOCS / "updates.json"
REPORT_JS = DOCS / "updates.js"
BASE_REF = "HEAD"


def committed(path):
    result = subprocess.run(
        ["git", "show", f"{BASE_REF}:{path}"], cwd=ROOT, capture_output=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def old_json(path, default):
    data = committed(path)
    return json.loads(data) if data else default


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def write_report_js(history):
    """Publish the report as a script as well as JSON so file:// previews work."""
    payload = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    REPORT_JS.write_text(f"window.MODEL_UPDATES={payload};\n", encoding="utf-8")


def image_hashes(product, previous=False):
    hashes = []
    for image in product.get("images", []):
        path = f"docs/{image}"
        data = committed(path) if previous else (DOCS / image).read_bytes()
        hashes.append(digest(data))
    return hashes


def current_image_hash(path):
    if not path.startswith("images/") or ".." in Path(path).parts:
        return None
    image = DOCS / path
    return digest(image.read_bytes()) if image.is_file() else None


def stamp_images(entry):
    images = entry.get("images", {})
    entry["image_counts"] = {key: len(images.get(key, [])) for key in ("added", "changed")}
    images["hashes"] = {
        path: current_image_hash(path)
        for key in ("added", "changed") for path in images.get(key, [])
    }


def prune_old_images(history):
    for run in history.get("updates", []):
        for entry in run.get("entries", []):
            images = entry.get("images", {})
            entry.setdefault("image_counts", {key: len(images.get(key, [])) for key in ("added", "changed")})
            hashes = images.get("hashes", {})
            for key in ("added", "changed"):
                images[key] = [
                    path for path in images.get(key, [])
                    if hashes.get(path) and current_image_hash(path) == hashes[path]
                ]
            images["hashes"] = {
                path: hashes[path] for key in ("added", "changed") for path in images.get(key, [])
            }


def compare_images(old, new, old_hashes, new_hashes):
    positions = defaultdict(deque)
    for index, value in enumerate(old_hashes):
        if value:
            positions[value].append(index)
    matched = []
    unmatched_new = []
    for index, value in enumerate(new_hashes):
        if value and positions[value]:
            matched.append((positions[value].popleft(), index))
        else:
            unmatched_new.append(index)
    unmatched_old = sorted(index for remaining in positions.values() for index in remaining)
    replaced_count = min(len(unmatched_old), len(unmatched_new))
    changed = unmatched_new[:replaced_count]
    added = unmatched_new[replaced_count:]
    # Put genuinely new or replaced pictures first; preserve the relative order of the rest.
    priority = set(unmatched_new)
    order = sorted(range(len(new_hashes)), key=lambda index: (index not in priority, index))
    moved = [{"from": before + 1, "to": order.index(after) + 1} for before, after in matched if before != order.index(after)]
    new["images"] = [new["images"][index] for index in order]
    return {
        "added": [new["images"][order.index(index)] for index in added],
        "changed": [new["images"][order.index(index)] for index in changed],
        "moved": moved,
        "removed_count": len(unmatched_old) - replaced_count,
    }


def changes_for(old, new):
    labels = {"name": "名称", "availability": "Availability", "price": "价格", "url": "商品链接"}
    fields = []
    for key, label in labels.items():
        before, after = old.get(key, ""), new.get(key, "")
        if before != after:
            fields.append({"field": label, "before": before, "after": after})
    old_properties, new_properties = old.get("properties", {}), new.get("properties", {})
    for key in sorted(set(old_properties) | set(new_properties)):
        before, after = old_properties.get(key, ""), new_properties.get(key, "")
        if before != after:
            fields.append({"field": key, "before": before, "after": after})
    return fields


def product_meta(product):
    properties = product.get("properties", {})
    return {
        "product_number": properties.get("Product number", ""),
        "scale": properties.get("Scale", ""),
    }


def publish():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    old_catalog = old_json("docs/catalog.json", {"products": []})
    previous = {item["id"]: item for item in old_catalog.get("products", [])}
    current = {item["id"]: item for item in catalog["products"]}
    old_state = old_json("state.json", {"items": {}}).get("items", {})
    state = json.loads((ROOT / "state.json").read_text(encoding="utf-8"))
    new_state = state.get("items", {})
    changed_ids = set().union(*(state.get("changes", {}).get(key, []) for key in ("added", "changed", "removed")))
    changed_ids |= set(previous) ^ set(current)
    entries = []
    for product_id in sorted(changed_ids):
        old, new = previous.get(product_id), current.get(product_id)
        if new is None:
            entries.append({"type": "removed", "id": product_id, "name": old["name"], "url": old.get("url", ""), **product_meta(old), "fields": [], "images": {}})
            continue
        fields = changes_for(old or {}, new) if old else []
        before_cover = old_state.get(product_id, {}).get("image_url", "")
        after_cover = new_state.get(product_id, {}).get("image_url", "")
        if old and before_cover != after_cover:
            fields.append({"field": "封面链接", "before": before_cover, "after": after_cover})
        images = compare_images(old or {}, new, image_hashes(old, True) if old else [], image_hashes(new))
        if old is None or fields or any(images.values()):
            entries.append({"type": "added" if old is None else "changed", "id": product_id, "name": new["name"], "url": new.get("url", ""), **product_meta(new), "fields": fields, "images": images})
    if not entries:
        history = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {"updates": []}
        write_report_js(history)
        print("No catalogue changes; update report unchanged")
        return
    catalog_text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    if CATALOG.read_text(encoding="utf-8") != catalog_text:
        CATALOG.write_text(catalog_text, encoding="utf-8")
    history = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {"updates": []}
    prune_old_images(history)
    for entry in entries:
        stamp_images(entry)
    history["updates"].insert(0, {"date": catalog["generated_at"], "entries": entries})
    REPORT.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report_js(history)
    print(f"Published update report: {len(entries)} products")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD", help="Committed version to compare with (default: HEAD)")
    BASE_REF = parser.parse_args().base
    publish()
