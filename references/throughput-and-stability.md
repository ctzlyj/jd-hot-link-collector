# 采集吞吐与稳定性（2026-10 实测）

## 任务页整轮复用
- 每一轮采集只创建一个任务标签页，整轮所有商品在该页内导航，轮次结束才关闭；原来每个商品建一个页，标签栏持续闪烁且占内存。
- 实现：`collect_signed.mjs` 持有 `taskTab`，`native_page.openNativePage(...,reuseTab)` 复用；异常隔离分支只关闭非复用页。
- 回归测试：`tests/test_batch_cli.mjs` 的 `one task tab is reused for the whole round`（断言 newTab=1、closed=1、navigation=商品数）。

## 单次页面调用批量取价
- 同一商品页内一次 `evaluate` 连续请求 10 个 SKU 并返回结果数组，替代「每 SKU 两三次浏览器往返」。
- 实测单 SKU 从约 1.5 秒降到 0.3-0.5 秒；签名仍由页面自身 SDK 生成，不出页面内存。
- 页面内轮询 25ms，单 SKU 超时 20 秒，超时立刻 `abortExpression` 并停轮，不重放。

## 单轮请求上限 45
- 单页连续约 50 次请求后浏览器命令开始报 `LOCAL_OR_TRANSPORT_ERROR`（大 SKU 商品反复触发）。
- 把 `JD_BATCH_MAX_REQUESTS` 设为 45，可在崩溃点前换页重开：实测错误从每 2-3 分钟一次降到整晚 0 次，代价只是每轮多一次页面加载。

## 素材下载固定 IPv4
- JD 图片 CDN 有 AAAA 记录，Python 先连 IPv6 会卡约 40 秒才回落到 IPv4；curl 直连 IPv4 只要 0.3 秒。
- `scripts/asset_paths.py` 导入时把 `socket.getaddrinfo` 固定为 `AF_INET`，单图 40 秒 → 0.3 秒。只影响媒体下载进程，不改业务接口。

## 详情图死链
- 商家 HTML 会给出只有域名或目录的坏 URL（如 `https://img10.360buyimg.com/imgzone/`），CDN 返 405，导致反复打包失败。
- `package_contract.ordered_detail_urls` 只接受含 `/jfs/` 或图片扩展名的 URL，其余直接丢弃；`stage_pending_materials.py` 同步过滤并把死链记入 `deadDetailUrls`。

## SKU 级下架与复核标记
- SKU 返回 `PRODUCT_UNAVAILABLE` 时写 `errors/<sku>.json` 后继续，不拦停整批。
- 复核模式（`--recheck-prices`）下同时给该 partial 写 `priceRecheckedAt`，否则该 SKU 每轮都会被重新请求，尾部永远清不完。

## 登录态降级后的价格复核（重要）
症状：某批商品全部显示「无促销价」，清单 100% 走原价兜底，比例明显异常。

原因：会话降级后京东只返回 `jdPrice`，不返回 `finalPrice`/`bestPromotion.purchasePrice`；采集器只能按原价兜底。

复核步骤：

1. 确认登录态已恢复：抽 1-2 个商品单采一次，看是否出现促销价。
2. 把该状态目录 `batch_driver_state.json` 的 `phase`/`workPhase` 置为 `RECHECK`，用驱动链跑 `collect_signed --recheck-prices`；`partial_data` 里的 `priceRecheckedAt` 记录进度，重复运行只补未复核的 SKU。
3. 复核完成后**必须**清空 `receipts/` 与 `packages/` 临时目录，并把旧成品目录移走再重新打包；否则打包器按旧 receipt 直接跳过，清单仍是旧价格，验收会报 `FULL_ROW_CONTENT_MISMATCH`。
4. 重新打包后按常规 `verify_batch.py` 验收，再 `deliver_batch.py` 出包；确认新包 CRC 通过后再删除旧包。

实测效果：日用1023 批 77/258、鲁碧1024 批 100/138 的商品补回了真实促销价。
