#!/usr/bin/env python3
"""Apple Store 库存监听，Python 3.9+，仅使用标准库。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser


DATA_DIR = Path(__file__).resolve().parent / "config" / "files"
PARTS_PER_REQUEST = 20
FAMILIES = {
    "iphone18pro": "iPhone 18 Pro",
    "iphone18promax": "iPhone 18 Pro Max",
    "iphoneduo": "iPhone Duo",
}
# code: (locale, title, official regional shop URL)
AREAS = {
    "cn": ("zh_CN", "中国大陆", "https://www.apple.com.cn/shop"),
    "hk": ("zh_HK", "中国香港", "https://www.apple.com/hk-zh/shop"),
    "tw": ("zh_TW", "中国台湾", "https://www.apple.com/tw/shop"),
    "sg": ("en_SG", "新加坡", "https://www.apple.com/sg/shop"),
    "jp": ("ja_JP", "日本", "https://www.apple.com/jp/shop"),
    "au": ("en_AU", "澳大利亚", "https://www.apple.com/au/shop"),
    "my": ("en_MY", "马来西亚", "https://www.apple.com/my/shop"),
    "us": ("en_US", "美国", "https://www.apple.com/shop"),
    "ca": ("en_CA", "加拿大", "https://www.apple.com/ca/shop"),
    "uk": ("en_GB", "英国", "https://www.apple.com/uk/shop"),
    "de": ("de_DE", "德国", "https://www.apple.com/de/shop"),
    "kr": ("ko_KR", "韩国", "https://www.apple.com/kr/shop"),
}


@dataclass(frozen=True)
class Item:
    code: str
    title: str


def read_data(filename):
    with (DATA_DIR / filename).open(encoding="utf-8") as stream:
        return json.load(stream)


def products_for(area):
    products = {}
    for selection in read_data(f"products_{AREAS[area][0]}.json"):
        for product in selection["products"]:
            family = product["familyType"]
            if family not in FAMILIES:
                continue
            color = selection["displayValues"]["dimensionColor"][product["dimensionColor"]]["value"]
            code = product["partNumber"]
            products[code] = Item(code, f"{FAMILIES[family]} - {color} - {product['dimensionCapacity']}")
    return sorted(products.values(), key=lambda item: (item.title, item.code))


def stores_for(area):
    stores = {}
    for region in read_data("stores.json"):
        if region["locale"] != AREAS[area][0]:
            continue
        groups = region["state"] if region.get("hasStates") else [region]
        for group in groups:
            for store in group.get("store", []):
                address = store["address"]
                places = list(dict.fromkeys(value for value in (address.get("stateName"), address.get("city")) if value))
                title = "-".join(places + [store["name"].strip()])
                stores[store["id"]] = Item(store["id"], title)
    return sorted(stores.values(), key=lambda item: (item.title, item.code))


def select_items(items, filters):
    """Each filter must match; multiple matches allow selecting a city or family."""
    if not filters:
        return items
    selected = {}
    for value in filters:
        exact = [item for item in items if item.code.casefold() == value.casefold()]
        matches = exact or [item for item in items if value.casefold() in item.title.casefold()]
        if not matches:
            raise ValueError(f"未找到匹配项：{value}")
        selected.update((item.code, item) for item in matches)
    return list(selected.values())


def split_selections(values):
    """Normalize repeated, comma-separated selectors; a bare option means all."""
    if values is None or any(value is None for value in values):
        return None
    result = [part.strip() for value in values for part in value.split(",") if part.strip()]
    if not result:
        raise ValueError("门店或型号选择列表不能为空")
    return result


def fetch_json(url, timeout, payload=None):
    headers = {"User-Agent": "Mozilla/5.0 AppleStoreHelper/1.0", "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    else:
        parsed = urlsplit(url)
        shop_prefix = parsed.path.split("/shop/", 1)[0] + "/shop"
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}{shop_prefix}/buy-iphone"
    request = Request(url, data=body, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def parse_availability(data, store_code, product_codes):
    """Parse the current retail API; missing or unrecognized states stay unknown."""
    try:
        stores = data["body"]["stores"]
        if not isinstance(stores, list):
            raise TypeError
        store = next(row for row in stores if row.get("storeNumber") == store_code)
        parts = store["partsAvailability"]
        if not isinstance(parts, dict):
            raise TypeError
    except (KeyError, TypeError, AttributeError, StopIteration) as error:
        raise ValueError("库存响应缺少所选门店或字段，无法判断库存") from error
    result = {}
    for code in product_codes:
        try:
            value = parts[code]["pickupDisplay"]
            result[code] = {"available": True, "unavailable": False, "ineligible": False}.get(value) if isinstance(value, str) else None
        except (KeyError, TypeError):
            result[code] = None
    return result


def check_store(area, store, products, timeout):
    statuses, errors = {}, []
    # The retail API truncates large product lists. Keep requests within 20 SKUs.
    for start in range(0, len(products), PARTS_PER_REQUEST):
        batch = products[start:start + PARTS_PER_REQUEST]
        query = {"pl": "true", "mts.0": "regular", "store": store.code}
        query.update((f"parts.{index}", product.code) for index, product in enumerate(batch))
        url = AREAS[area][2] + "/retail/pickup-message?" + urlencode(query)
        try:
            data = fetch_json(url, timeout)
            statuses.update(parse_availability(data, store.code, [p.code for p in batch]))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            # Preserve successful batches; missing results stay unknown.
            detail = f"HTTP {error.code}" if isinstance(error, HTTPError) else type(error).__name__
            errors.append(f"第 {start // PARTS_PER_REQUEST + 1} 批查询失败（{detail}）")
    return store, statuses, "；".join(errors) + "，该批库存未知" if errors else None


def validate_bark_url(value):
    if not value:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Bark 地址应为 http(s)://主机/设备Key，不带查询参数或片段")
    return value.rstrip("/")


def notify_bark(base, message, bag_url, timeout):
    # JSON POST avoids putting notification text or the bag URL in a URL path.
    result = fetch_json(base, timeout, {"title": "有货提醒", "body": message, "url": bag_url})
    if not isinstance(result, dict) or result.get("code") != 200:
        raise ValueError("Bark 返回失败")


def watch(args, stores, products):
    bag_url = AREAS[args.area][2] + "/bag"
    print(f"国家或地区：{AREAS[args.area][1]}；{len(stores)} 家门店 × {len(products)} 个型号", flush=True)
    for store in stores:
        print(f"  {store.code}  {store.title}", flush=True)
    for product in products:
        print(f"  {product.code}  {product.title}", flush=True)
    previous = set()
    with ThreadPoolExecutor(max_workers=min(4, len(stores))) as executor:
        while True:
            results = list(executor.map(lambda store: check_store(args.area, store, products, args.timeout), stores))
            available, unknown, total = set(), 0, 0
            messages = []
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for store, statuses, error in results:
                if error:
                    print(f"[{stamp}] {store.title}：{error}", file=sys.stderr, flush=True)
                for product in products:
                    total += 1
                    status = statuses.get(product.code)
                    if status is None:
                        unknown += 1
                    elif status:
                        key = (store.code, product.code)
                        available.add(key)
                        message = f"{store.title} {product.title} ({product.code}) 有货"
                        print(f"[{stamp}] {message}", flush=True)
                        if key not in previous:
                            messages.append(message)
            print(f"[{stamp}] 有货 {len(available)} / 无货 {total-len(available)-unknown} / 未知 {unknown}", flush=True)
            if messages:
                print(f"\a购物袋：{bag_url}", flush=True)
                if args.bark_url:
                    try:
                        notify_bark(args.bark_url, "\n".join(messages), bag_url, args.timeout)
                    except (OSError, ValueError) as error:
                        print(f"Bark 通知失败（{type(error).__name__}），请查看上面的有货记录。", file=sys.stderr, flush=True)
                if args.open_bag:
                    webbrowser.open(bag_url)
            if available and not args.keep_watching:
                return 0
            if args.once:
                return 0 if available else (2 if unknown else 1)
            # Unknown results must not erase known in-stock state and cause duplicate notifications.
            unknown_keys = {(store.code, product.code) for store, statuses, _ in results for product in products if statuses.get(product.code) is None}
            previous = available | (previous & unknown_keys)
            time.sleep(args.interval)


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("必须为大于 0 的有限数值")
    return number


def area_code(value):
    value = {"gb": "uk"}.get(value.casefold(), value)
    for code, (locale, title, _) in AREAS.items():
        if value.casefold() in (code, locale.casefold(), title.casefold()):
            return code
    raise argparse.ArgumentTypeError("不支持的国家或地区；使用 list-areas 查看")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-areas", help="列出国家或地区")
    for name, help_text in (("list-stores", "列出门店及编号，可用 --filter 筛选"), ("list-products", "列出型号及 SKU，可用 --filter 筛选"), ("watch", "监听库存")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--area", type=area_code, default="cn", help="国家或地区代码，默认 cn")
        if name == "list-stores":
            command.add_argument("--filter", action="append", help="模糊匹配门店名称或精确编号，可重复")
        elif name == "list-products":
            command.add_argument("--filter", action="append", help="型号、颜色、容量或 SKU，可重复")
        else:
            command.add_argument("--store", action="append", help="门店编号或名称关键词，支持逗号分隔或重复；默认全部门店")
            command.add_argument("--filter", action="append", help="进一步筛选门店名称或精确编号，可重复")
            command.add_argument("--product", action="append", nargs="?", const=None, help="SKU 或型号关键词，支持逗号分隔或重复；省略或不带值表示全部型号")
            command.add_argument("--interval", type=positive_number, default=10, help="轮次间隔秒数，默认 10，最低 1")
            command.add_argument("--timeout", type=positive_number, default=10, help="每个请求超时秒数，默认 10")
            command.add_argument("--once", action="store_true", help="仅查询一轮")
            command.add_argument("--keep-watching", action="store_true", help="有货后继续监听，仅新增有货状态触发通知")
            command.add_argument("--open-bag", action="store_true", help="有货时打开购物袋")
            command.add_argument("--bark-url", default=os.environ.get("BARK_URL", ""), help="Bark 地址，建议通过 BARK_URL 环境变量设置")
    args = parser.parse_args(argv)
    try:
        if args.command == "list-areas":
            for code, (locale, title, _) in AREAS.items():
                print(f"{code}\t{locale}\t{title}")
        elif args.command == "list-stores":
            stores = stores_for(args.area)
            if not stores:
                print(f"{AREAS[args.area][1]}：暂无门店数据")
                return 0
            for item in select_items(stores, args.filter):
                print(f"{item.code}\t{item.title}")
        elif args.command == "list-products":
            products = products_for(args.area)
            if not products:
                print(f"{AREAS[args.area][1]}：暂无型号数据")
                return 0
            for item in select_items(products, args.filter):
                print(f"{item.code}\t{item.title}")
        else:
            if args.interval < 1:
                raise ValueError("轮次间隔不能小于 1 秒")
            args.bark_url = validate_bark_url(args.bark_url)
            available_stores = stores_for(args.area)
            if not available_stores:
                raise ValueError(f"{AREAS[args.area][1]}：暂无门店数据")
            stores = select_items(available_stores, split_selections(args.store))
            stores = select_items(stores, args.filter)
            products = select_items(products_for(args.area), split_selections(args.product))
            if not stores or not products:
                raise ValueError("所选国家或地区没有可用门店或型号")
            return watch(args, stores, products)
    except KeyboardInterrupt:
        print("\n已停止监听。", file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
