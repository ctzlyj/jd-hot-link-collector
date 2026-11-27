"""Offline regression for normal collection stages and both POP dispatchers."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from PIL import Image


STAGES = {"prepare": "prepare_batch.py", "package": "package_live.py", "verify": "verify_batch.py",
          "deliver": "deliver_batch.py", "shop-table": "shop_table.py", "fallback-verify": "batch_driver/verify_batch_fallback.py"}


def invoke(command, env, expect=0):
    proc = subprocess.run(command, env=env, capture_output=True, encoding="utf8", errors="replace", timeout=120)
    accepted = (expect,) if isinstance(expect, int) else expect
    if proc.returncode not in accepted:
        raise AssertionError((command, proc.returncode, proc.stdout[-900:], proc.stderr[-600:]))
    return proc.stdout + proc.stderr if proc.returncode else proc.stdout


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf8")


def run(root, prefix=None):
    merchant = (root / "scripts/merchant.py").is_file()
    with tempfile.TemporaryDirectory(prefix="collection-contract-") as directory:
        workspace = Path(directory)
        state = workspace / "state"
        out = workspace / "output"
        out.mkdir()
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "HEIDENG_MERCHANT_HOME": str(state)}
        for name in list(env):
            if name.startswith(("JD_COLLECTOR_", "JD_BATCH_", "HEIDENG_COLLECTION_")):
                del env[name]
        if merchant:
            installed = workspace / "skills"
            invoke([sys.executable, str(root / "install.py"), "--state", str(state), "--skills-dir", str(installed),
                    "--offline", "--no-auto-update"], env)
            root = installed / "heideng-ops-agent-merchant"
        stage = (state / "mature/collection/batches" / sha256(str(out.resolve()).encode()).hexdigest()
                 if merchant else out / ".collector_state")
        env.update(JD_COLLECTOR_ROOT=str(out), JD_COLLECTOR_STATE_DIR=str(stage), JD_BATCH_STATE_DIR=str(stage))

        def call(tool, args, expect=0):
            if prefix:
                cmd = [*prefix, tool]
            elif merchant:
                entry = [] if tool == "prepare" else ["--entry", "scripts/" + STAGES[tool]]
                cmd = [sys.executable, str(root / "scripts/merchant.py"), "--state", str(state),
                       "run", *entry, "collection", "--"]
            else:
                cmd = [sys.executable, str(root / "scripts" / STAGES[tool])]
            return invoke([*cmd, "--root", str(out), *map(str, args)], env, expect)

        pid, sibling, unseen, spu = "10000000000001", "10000000000002", "10000000000003", "20000000000001"
        source = workspace / "products.xlsx"
        wb = Workbook()
        wb.active.append(["synthetic"])
        for sku in (pid, unseen):
            wb.active.append([None, "Fixture " + sku, sku] + [None]*9 + ["https://item.jd.com/" + sku + ".html"])
        wb.save(source)
        wb.close()
        assert json.loads(call("prepare", ["--input", source]).splitlines()[-1])["sourceProducts"] == 2
        # Every asset and every price observation is local; an accidental media fetch cannot use a store.
        url = "http://127.0.0.1:9/fixture.jpg"
        data = {"ok": True, "login": True, "responseSku": pid, "title": "Fixture", "p": "20", "pp": "8",
                "priceSource": "warePriceGatherVO.finalPrice", "realSpuId": spu, "carousel": [{"u": url, "v": []}],
                "crumbs": [], "attrs": [], "colorSize": [{"dim": 1, "buttons": [
                    {"no": "1", "text": "A", "skuId": pid, "skuList": [pid]},
                    {"no": "2", "text": "B", "skuId": sibling, "skuList": [sibling]}]}]}
        save(stage / "data" / (pid + ".json"), {"source": "live_native_page", "data": data})
        save(stage / "details_ordered" / (spu + ".json"), [])
        buf = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(buf, "JPEG")
        cache = stage / "asset_cache" / (sha256(url.encode()).hexdigest() + ".jpg")
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(buf.getvalue())
        call("package", [])
        call("verify", [])
        def validation():
            return json.loads((stage / "independent_validation.json").read_bytes())
        assert validation()["results"][0]["state"] == "PRICE_PENDING"
        # A pre-existing pacing/environment flag cannot authorize another batch's original price.
        env["JD_BATCH_ORIGINAL_PRICE_FALLBACK"] = "1"
        refusal = call("fallback-verify", [], expect=(1, 2))
        assert "ORIGINAL_PRICE_FALLBACK_AUTHORIZATION_REQUIRED" in refusal
        assert not (stage / "price_fallback.json").exists()
        save(stage / "errors" / (sibling + ".json"), {"sku": sibling, "reason": "PRODUCT_UNAVAILABLE"})
        call("package", [])
        call("verify", [])
        assert [r["state"] for r in validation()["results"]] == ["VERIFIED", "MAIN_PENDING"]
        receipt = json.loads(call("deliver", ["--name", "fixture"]).splitlines()[-1])
        assert (receipt["scope"], receipt["products"], receipt["complete"]) == (2, 1, False)
        assert receipt["pending"] == [{"keyword": "synthetic", "sourceSku": unseen, "state": "MAIN_PENDING"}]
        archive, = out.glob("*.zip")
        with ZipFile(archive) as pack:
            assert pack.testzip() is None
        diff = json.loads(call("deliver", ["--previous-zip", archive]).splitlines()[-1])
        assert diff["products"] == 0 and diff["excludedByPreviousArchive"] == [pid] and diff["pending"] == receipt["pending"]
        # A separate request for original-price fallback uses its own outputs and permission.
        out = workspace / "fallback-output"
        out.mkdir()
        stage = (state / "mature/collection/batches" / sha256(str(out.resolve()).encode()).hexdigest()
                 if merchant else out / ".collector_state")
        env.update(JD_COLLECTOR_ROOT=str(out), JD_COLLECTOR_STATE_DIR=str(stage), JD_BATCH_STATE_DIR=str(stage))
        call("prepare", ["--input", source])
        save(stage / "data" / (pid + ".json"), {"source": "live_native_page", "data": data})
        save(stage / "details_ordered" / (spu + ".json"), [])
        cache = stage / "asset_cache" / (sha256(url.encode()).hexdigest() + ".jpg")
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(buf.getvalue())
        save(stage / "partial_data" / (sibling + ".json"),
             {"source": "live_native_page_arrival_pending", "data": {**data, "responseSku": sibling, "pp": None}})
        call("package", [])   # The original-price environment signal alone cannot supply a price.
        assert any(row["state"] == "SKU_PRICES_PENDING" for row in json.loads((stage / "package_report.json").read_bytes()))
        call("package", ["--allow-original-price-fallback"])
        metadata = json.loads((stage / "packages" / pid / "package_metadata.json").read_bytes())
        marker = json.loads((stage / "price_fallback.json").read_bytes())["marker"]
        assert metadata["priceSources"][sibling] == marker and float(metadata["arrivalPrices"][sibling]) == 20
        call("fallback-verify", [])
        assert json.loads((stage / "price_fallback.json").read_bytes())["marker"].startswith("original_price_user_authorized_")

        # Exercise the unmodified packaging command at its public-image transport boundary.
        # Only source bytes are substituted. The final independent verifier still runs through the dispatcher.
        import importlib
        from unittest.mock import patch
        from contextlib import redirect_stdout
        from io import StringIO
        import requests
        out = workspace / "variant-output"
        out.mkdir()
        stage = (state / "mature/collection/batches" / sha256(str(out.resolve()).encode()).hexdigest()
                 if merchant else out / ".collector_state")
        env.update(JD_COLLECTOR_ROOT=str(out), JD_COLLECTOR_STATE_DIR=str(stage), JD_BATCH_STATE_DIR=str(stage))
        call("prepare", ["--input", source])
        original_url = "https://img14.360buyimg.com/n1/jfs/fixture-source.jpg"
        alt = original_url.replace("/n1/", "/n12/")
        observed = {**data, "carousel": [{"u": original_url, "v": []}], "colorSize": []}
        save(stage / "data" / (pid + ".json"), {"source": "live_native_page", "data": observed})
        save(stage / "details_ordered" / (spu + ".json"), [])
        scripts = root / ("mature/collection/scripts" if merchant else "scripts")
        with patch.dict(os.environ, {**env, "HEIDENG_COLLECTION_ROOT": str(out), "HEIDENG_COLLECTION_STATE_DIR": str(stage)}), \
                patch.object(sys, "argv", ["package_live.py", "--root", str(out)]), \
                patch.object(sys, "path", [str(scripts), str(root), *sys.path]):
            package = importlib.import_module("package_live")
            assets = importlib.import_module("asset_paths")
            for code in (403, 429):
                response = requests.Response()
                response.status_code = code
                with patch.object(assets, "get_public", side_effect=requests.HTTPError(response=response)) as fetch, \
                        redirect_stdout(StringIO()):
                    package.main()
                assert [c.args[0] for c in fetch.call_args_list] == [original_url]
                record = json.loads((stage / "package_report.json").read_bytes())[0]
                assert record["state"] == "MATERIAL_ERROR" and record["httpStatus"] == code
            with patch.object(assets, "get_public", return_value=b"<html>Login required</html>") as fetch, \
                    redirect_stdout(StringIO()):
                package.main()
            assert [c.args[0] for c in fetch.call_args_list] == [original_url]
            assert json.loads((stage / "package_report.json").read_bytes())[0]["state"] == "MATERIAL_ERROR"
            def image_response(url):
                if url == original_url:
                    return b"\xff\xd8truncated-jpeg"
                assert url == alt, url
                return buf.getvalue()
            with patch.object(assets, "get_public", side_effect=image_response) as fetch, redirect_stdout(StringIO()):
                package.main()
            assert [c.args[0] for c in fetch.call_args_list] == [original_url, alt]
        call("verify", [])
        assert validation()["results"][0]["state"] == "VERIFIED", validation()
        metadata_file = stage / "packages" / pid / "package_metadata.json"
        metadata = json.loads(metadata_file.read_bytes())
        note, = metadata["sourceNotes"]
        assert note["originalUrl"] == original_url and note["variantUrl"] == alt and note["alsoUsedFor"]
        note["variantUrl"] = alt.replace("fixture-source.jpg", "wrong-product.jpg")
        save(metadata_file, metadata)
        call("verify", [])
        assert validation()["results"][0]["state"] == "VALIDATION_ERROR"
        shops = workspace / "shops.xlsx"
        wb = Workbook()
        wb.active.append(["店铺", "商品标签"])
        wb.active.append([123456, "fixture"])
        wb.active.append([987654, "pending"])
        wb.active.append(["Unresolved name", "unidentified"])
        wb.save(shops)
        wb.close()
        source_sha = sha256(shops.read_bytes()).hexdigest()
        records = workspace / "authorized-counts.json"
        save(records, {"shops": {"123456": {"skuCount": 7, "productCount": 3, "missing": []}}})
        report = json.loads(call("shop-table", ["--input", shops, "--results", records]).splitlines()[-1])
        assert report["shopsWritten"] == 1 and report["pendingShopIds"] == ["987654"]
        book = load_workbook(report["output"], read_only=True)
        try:
            assert book.active["C2"].value == 7 and book.active["C3"].value is None
        finally:
            book.close()
        assert source_sha == sha256(shops.read_bytes()).hexdigest()
        print(json.dumps({"scope": 2, "verified": 1, "pending": 1, "shopCountsWritten": 1, "variantReadback": "verified",
                          "restrictionsRetried": 0, "tamperedVariantRejected": True, "platformWrites": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-json", help="internal dispatcher prefix ending in collection")
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], json.loads(args.entry_json) if args.entry_json else None)
