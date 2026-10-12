---
name: jd-hot-link-collector
description: 将京东爆品链接或关键词分段的商品清单批量采集为可审核素材包：逐SKU真实到手价（前台finalPrice优先，禁止原价补齐）、前台SKU顺序、主图/详情图/SKU图、主图视频单独文件夹、22列商品信息表、断点续采和严格的频控熔断。用户给京东链接清单并要求“采集/搬运素材/整理素材包但不上架”时使用；不用于发布上架、营销报名或绕过平台风控。
---

# 京东爆品链接批量采集

把“采集素材 + 真实到手价 + 断点恢复 + 独立验收”作为一个可恢复事务。只采集，不上架、不改图。

## 输入约定

- 清单为 `.xlsx`：第1列为关键词行（仅A列有词），其后是表头行；商品行：C列=商品ID，M列=商品链接，B列=标题。
- 商品ID集合必须与链接集合一致；链接列允许整体错位（脚本会识别并按ID集合校验）；重复行保留行号记录、按唯一商品去重。
- 仅处理用户明确授权的链接和素材。

## 流程

1. 生成清单与审计（无网络请求）：
   `python -X utf8 scripts/prepare_batch.py --input <清单.xlsx> --root <输出根目录>`
2. 在已登录浏览器中建立一个任务专属商品页（不绑定工作页），把 `{session, tab, idleTimeout, windowMode:"background", probeSku}` 写入 `<root>/.collector_state/browser_context.json`；详见 `references/browser-session-setup.md`。
3. 采集主路径为点击驱动（新标签页逐商品、真实规格点击、原生响应捕获）：
   `node scripts/click_collector.mjs --root=<root>`
   已知限制：goto重载后的页面点击失效；同页第2个起程序化请求会被静默挂起；商品间导航间隔不足会触发验证页（脚本内置60秒）。
4. 长冷却后恢复采集时，第一个业务动作必须是真实规格点击测试（禁止先发脚本请求）：
   `node scripts/clean_session_click_test.mjs --root=<root>`
5. 备用路径：程序化SDK请求采集（仅在单次探测验证通过后使用；30秒间隔、每轮≤20请求，成功缓存不重采）：
   `node scripts/collect_signed.mjs --run --root=<root> --interval-ms=30000 --max-requests=20`
6. 生成完整商品包（缺任一SKU到手价即不打包）：
   `python -X utf8 scripts/package_live.py --root=<root>`
7. 独立验收（逐行价格/顺序/目录/图片/视频）：
   `python -X utf8 scripts/verify_batch.py --root=<root>`
- 需要自动等待-探测-续采时：`python -X utf8 scripts/supervisor.py --root=<root>`（403/429按递增冷却，验证/登录/未知结果立即停）。
- 点击驱动被限流后自动恢复：`python -X utf8 scripts/click_supervisor.py --root=<root>`（小时级单页探测，验证/登录问题停下等人工，最多5次）。

## 输出结构

`<root>/<关键词>/<商品标题>/` 内：`主图/`、`详情图/`、`SKU图/`、`主图视频/`（仅存在视频时）、`商品信息.xlsx`。同级标题冲突时追加SKU后缀。

## 价格与顺序契约

- 到手价优先取 `warePriceGatherVO.priceItemList` 中未划线的 `priceType="finalPrice"`；无该项才回退 `bestPromotion.purchasePrice`；普通 `jdPrice`、原价、清单历史价一律不得补齐。
- SKU行顺序按 `colorSizeVO.colorSizeList` 各维度按钮 `no` 升序，双维度取真实SKU交集，禁止笛卡尔积或采集器默认顺序。
- 商品级字段（标题、货号、属性、类目）只保留在排序后的首行。

## 停止条件

- 出现 `pc-frequent-pro.pf.jd.com` PC频控页、403、429（尊重 `Retry-After`）、验证页或登录失效：立即熔断，本轮停止，不换账号/IP/端点绕过。
- 403会污染当前会话：触发后真实点击和文档导航都可能被重定向到频控页。下次恢复必须长冷却后先做真实规格点击测试。
- 请求结果未知时不重放；缺价商品保留 `partial_data` 与 `ARRIVAL_PRICE_PENDING` 状态，不算完成。
- 30秒/20请求只是本地保护值，不是平台安全阈值，更不是已验证的“解除限流”方案。

## 断点

全部状态在 `<root>/.collector_state/`：`data/`（有效价格快照）、`partial_data/`（缺价主数据）、`errors/`、`request_clock.json`（跨进程请求间隔）、`receipts/`、`independent_validation.json`。重跑只补缺失项。

## 验证

```
node --test tests/test_browser_worker.mjs tests/test_request_policy.mjs tests/test_collection_policy.mjs tests/test_task_context.mjs
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

参考：`references/browser-session-setup.md`、`references/rate-limit-and-recovery.md`、`references/price-and-sku-contract.md`、`references/package-contract.md`
