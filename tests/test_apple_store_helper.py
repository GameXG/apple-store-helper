import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apple_store_helper as helper


def response(parts, store="R683"):
    return {"body": {"stores": [{
        "storeNumber": store,
        "partsAvailability": {code: {"pickupDisplay": state} for code, state in parts.items()},
    }]}}


class CatalogTests(unittest.TestCase):
    def test_all_regions_have_only_current_families_and_stores(self):
        for area in helper.AREAS:
            with self.subTest(area=area):
                products = helper.products_for(area)
                self.assertEqual(len(products), 40)
                self.assertEqual(len({p.code for p in products}), 40)
                self.assertEqual(len(helper.select_items(products, ["Duo"])), 8)
                self.assertEqual(len(helper.select_items(products, ["18 Pro Max"])), 16)
                self.assertTrue(all("17" not in p.title and "Air" not in p.title for p in products))
                self.assertTrue(helper.stores_for(area))

    def test_select_exact_and_keyword_union_deduplicates(self):
        products = helper.products_for("cn")
        duo = helper.select_items(products, ["duo"])
        self.assertEqual(helper.select_items(products, ["duo", duo[0].code.lower()]), duo)
        self.assertEqual(helper.select_items(products, [duo[0].code.lower()]), [duo[0]])
        self.assertGreater(len(helper.select_items(helper.stores_for("cn"), ["上海"])), 1)
        with self.assertRaises(ValueError):
            helper.select_items(products, ["not-a-product"])

    def test_locale_alias_and_invalid_numbers(self):
        self.assertEqual(helper.area_code("zh_CN"), "cn")
        for value, code in [("gb", "uk"), ("en_US", "us"), ("ko_KR", "kr")]:
            self.assertEqual(helper.area_code(value), code)
        for value in ["nan", "inf", "0", "-1"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                helper.positive_number(value)


class ListingCommandTests(unittest.TestCase):
    @patch.object(helper, "fetch_json")
    def test_filter_lists_matches_without_starting_monitor(self, fetch):
        cases = [
            (["list-stores", "--filter", "上海"], helper.stores_for("cn"), "上海"),
            (["list-stores", "--area", "hk", "--filter", "canton"], helper.stores_for("hk"), "canton"),
            (["list-products", "--filter", "Duo"], helper.products_for("cn"), "Duo"),
        ]
        for argv, items, keyword in cases:
            with self.subTest(argv=argv):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(helper.main(argv), 0)
                expected = [f"{item.code}\t{item.title}" for item in items
                            if keyword.casefold() in item.title.casefold()]
                self.assertTrue(expected)
                self.assertEqual(output.getvalue().splitlines(), expected)
        fetch.assert_not_called()

    def test_list_stores_lists_every_store_in_selected_area(self):
        for area in ("cn", "hk"):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(helper.main(["list-stores", "--area", area]), 0)
            self.assertEqual(output.getvalue().splitlines(),
                             [f"{s.code}\t{s.title}" for s in helper.stores_for(area)])

    def test_list_areas_lists_codes_and_names(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(helper.main(["list-areas"]), 0)
        self.assertEqual(output.getvalue().splitlines(),
                         [f"{code}\t{locale}\t{title}"
                          for code, (locale, title, _) in helper.AREAS.items()])

    @patch.object(helper, "fetch_json")
    def test_removed_countries_are_rejected_before_network_requests(self, fetch):
        self.assertEqual(len(helper.AREAS), 12)
        for area in ("id", "sa", "id_ID", "en_SA", "印度尼西亚", "沙特阿拉伯"):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_info:
                helper.main(["list-stores", "--area", area])
            self.assertEqual(exit_info.exception.code, 2)
        fetch.assert_not_called()

    def test_removed_store_search_alias_is_rejected(self):
        for argv in (["--store-search", "上海"], ["list-stores", "--store-search", "上海"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_info:
                helper.main(argv)
            self.assertEqual(exit_info.exception.code, 2)

    def test_regular_watch_help_is_unchanged(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exit_info:
            helper.main(["watch", "--help"])
        self.assertEqual(exit_info.exception.code, 0)
        self.assertIn("--product", output.getvalue())


class AvailabilityTests(unittest.TestCase):
    def test_only_documented_pickup_states_are_stock_results(self):
        result = helper.parse_availability(response({"a": "available", "b": "unavailable", "c": "ineligible", "d": "unexpected", "e": True}), "R683", "abcdef")
        self.assertEqual(result, {"a": True, "b": False, "c": False, "d": None, "e": None, "f": None})

    def test_legacy_response_is_rejected(self):
        data = {"body": {"content": {"pickupMessage": {"stores": []}}}}
        with self.assertRaises(ValueError):
            helper.parse_availability(data, "R683", ["a"])

    def test_wrong_store_and_malformed_response_are_errors(self):
        for data in [response({}, "R390"), {}, {"body": None}, response({})]:
            # Empty valid store data is unknown per SKU; absent store/schema is an error.
            if data == response({}):
                self.assertEqual(helper.parse_availability(data, "R683", ["a"]), {"a": None})
            else:
                with self.assertRaises(ValueError):
                    helper.parse_availability(data, "R683", ["a"])

    @patch.object(helper, "fetch_json")
    def test_official_regional_url_and_sku_encoding(self, fetch):
        product = helper.products_for("cn")[0]
        fetch.return_value = response({product.code: "available"})
        _, statuses, error = helper.check_store("cn", helper.Item("R683", "环球港"), [product], 3)
        self.assertIsNone(error)
        self.assertTrue(statuses[product.code])
        url, timeout = fetch.call_args.args
        self.assertEqual(urlsplit(url).hostname, "www.apple.com.cn")
        self.assertEqual(urlsplit(url).path, "/shop/retail/pickup-message")
        self.assertEqual(parse_qs(urlsplit(url).query)["mts.0"], ["regular"])
        self.assertEqual(parse_qs(urlsplit(url).query)["pl"], ["true"])
        self.assertEqual(parse_qs(urlsplit(url).query)["parts.0"], [product.code])
        self.assertIn("%2F", url)
        self.assertEqual(timeout, 3)

    @patch.object(helper, "fetch_json")
    def test_http_failure_is_unknown(self, fetch):
        fetch.side_effect = HTTPError("https://example.com", 503, "unavailable", {}, None)
        _, statuses, error = helper.check_store("cn", helper.Item("R683", "环球港"), [helper.Item("a", "Duo")], 3)
        self.assertEqual(statuses, {})
        self.assertIn("HTTP 503", error)

    @patch.object(helper, "fetch_json")
    def test_large_catalog_is_batched_without_losing_successful_results(self, fetch):
        products = [helper.Item(str(i), "Duo") for i in range(40)]
        fetch.side_effect = [response({str(i): "available" for i in range(20)}),
                             HTTPError("https://example.com", 503, "unavailable", {}, None)]
        _, statuses, error = helper.check_store("cn", helper.Item("R683", "环球港"), products, 3)
        self.assertEqual(len(statuses), 20)
        self.assertTrue(all(statuses.values()))
        self.assertIn("第 2 批", error)
        queries = [parse_qs(urlsplit(call.args[0]).query) for call in fetch.call_args_list]
        self.assertEqual(queries[0]["parts.19"], ["19"])
        self.assertEqual(queries[1]["parts.0"], ["20"])
        self.assertTrue(all("parts.20" not in query for query in queries))

    @patch.object(helper, "urlopen")
    def test_bark_post_encodes_unicode_and_bag_url(self, open_url):
        open_url.return_value.__enter__.return_value = io.StringIO('{"code":200}')
        helper.notify_bark("https://api.day.app/test-key", "蓝色 / 256GB? 有货", "https://www.apple.com.cn/shop/bag", 3)
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data)["body"], "蓝色 / 256GB? 有货")
        self.assertEqual(json.loads(request.data)["url"], "https://www.apple.com.cn/shop/bag")


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.store = helper.Item("R683", "环球港")
        self.product = helper.Item("P/A", "iPhone Duo")
        self.args = argparse.Namespace(area="cn", timeout=1, interval=1, once=True,
                                       keep_watching=False, open_bag=False, bark_url="")
        self.output = io.StringIO()

    def run_watch(self):
        with redirect_stdout(self.output), redirect_stderr(self.output):
            return helper.watch(self.args, [self.store], [self.product])

    def test_once_exit_codes(self):
        for status, expected in [(True, 0), (False, 1), (None, 2)]:
            with patch.object(helper, "check_store", return_value=(self.store, {"P/A": status}, None)):
                self.assertEqual(self.run_watch(), expected)

    @patch.object(helper, "notify_bark", side_effect=ValueError("failed"))
    def test_notification_failure_does_not_hide_stock(self, notify):
        self.args.bark_url = "https://api.day.app/test"
        with patch.object(helper, "check_store", return_value=(self.store, {"P/A": True}, None)):
            self.assertEqual(self.run_watch(), 0)
        self.assertIn("通知失败", self.output.getvalue())

    @patch.object(helper, "notify_bark")
    def test_unknown_round_does_not_duplicate_notification(self, notify):
        self.args.once, self.args.keep_watching = False, True
        self.args.bark_url = "https://api.day.app/test"
        rounds = [(self.store, {"P/A": state}, None) for state in [True, None, True, False, True]]
        with patch.object(helper, "check_store", side_effect=rounds), patch.object(helper.time, "sleep", side_effect=[None, None, None, None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                self.run_watch()
        self.assertEqual(notify.call_count, 2)

    def test_invalid_cli_filter_never_queries(self):
        with patch.object(helper, "fetch_json") as fetch, redirect_stderr(self.output):
            self.assertEqual(helper.main(["watch", "--store", "R683", "--product", "17", "--once"]), 2)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
