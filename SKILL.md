---
version: "1.0.11"
name: jd-hot-link-collector
description: 将京东商品链接清单采集为关键词/商品标题命名的素材包，接口优先按每个源商品的原生上下文读取逐SKU真实到手价和前台SKU顺序，提供点击备用、主图/详情图/SKU图/主图视频、22列商品信息表、断点恢复及独立验收。用户要求采集或搬运素材但不上架时使用；不发布、不修图、不绕过平台登录或风控。
---

# 京东链接素材采集

用户可以交办采集链接、核对一批 SKU 的到手价、补齐已有素材包，或整理店铺统计。宿主按当前目标选用准备、取证、打包、独立核验与增量交付工具，沿用已有任务目录和授权。交付回执同时说明本次交出的商品和原范围内仍待补的商品。

从清单或本机回执开始就可以做准备和核验。只有本次需要读页面时，才检查对应的浏览器和已授权会话，参考 references/browser-session-setup.md。首次部署或排查依赖可运行 python -X utf8 scripts/self_check.py。只有本批范围明确接受原价备用时才采用该价格，并随交付记录来源。

## 输入与输出

- 关键词分段 `.xlsx`：仅 A 列有词的行作为关键词；商品行 B=标题、C=商品 ID、M=链接。按关键词核对 ID/链接集合，链接列错位留审计，重复来源保留行号但只采一个包。也兼容 A=关键词、C=标题、D=商品 ID、无链接列的采集表（自动识别，`input_audit.json` 记录 `layout`）；跨关键词重复 ID 保留首个并写 `crossKeywordDuplicates` 审计。
- 单链接或普通链接列表可由助手转换成相同 `keyword_tasks.json` 格式；禁止猜商品 ID 或扩大输入范围。
- `<root>/<关键词>/<商品标题>/` 包含 `主图/`、`详情图/`、`SKU图/`、`主图视频/`、`商品信息.xlsx`。无视频时保留空视频目录。未知字段空白，真实 JPEG，视频原件单独存放。
- 状态放 `<root>/.collector_state/`，不会自动读取或复制另一台机器的账号、Cookie、设备信息。

## 执行

1. `python -X utf8 scripts/prepare_batch.py --input <xlsx> --root <目录>`：无网络解析并保存源哈希、行号、关键词与去重范围。
2. 配置任务会话及本机 WebCLI 模块路径到 `.collector_state/browser_context.json`。接口采集自己创建商品任务页，旧 tab 不是跨机器身份凭据。
3. **接口优先**：`node scripts/collect_signed.mjs --run --root=<目录> --interval-ms=50 --max-requests=45`
   每源商品加载一次原生上下文；同商品 SKU 用页面官方 SDK + XHR，不逐 SKU 翻页。不再逐 SKU 往返：一轮只建一个任务标签页并复用，页内一次调用批量取 10 个 SKU。不跨商品复用旧设备上下文，签名和设备头仅在浏览器内存。吞吐与稳定性细节见 `references/throughput-and-stability.md`。
4. `COOLDOWN_REQUIRED`：保存断点，等待后重新运行；有效原生/接口价格缓存均复用。若是缺价，普通取数阶段继续采其他商品，补价阶段加 `--recheck-prices` 有界核验；默认缺价保持 `ARRIVAL_PRICE_PENDING`，不打包。
5. 接口失败先读 `references/rate-limit-and-recovery.md` 分流，检查真实失败原因。仅正常页面仍可访问、接口无法覆盖时才使用 `node scripts/click_collector.mjs --root=<目录>`。403/429/频控/验证后先停，不能自动切工具绕过。
6. `python -X utf8 scripts/package_live.py --root=<目录>`：全部 SKU 有到手价才生成完整包；`python -X utf8 scripts/verify_batch.py --root=<目录>`：逐行与源缓存独立验收。
7. `python -X utf8 scripts/deliver_batch.py --root=<目录> --name <批次名> [--max-size-mb 950] [--previous-zip <旧包.zip>] [--overwrite]`：仅打包 `VERIFIED` 商品，生成上架清单（SKU 数、图片/视频数、用原价 SKU 数、到手价区间）与 CRC 校验压缩包。`--max-size-mb` 按关键词整组拆分（如微信单包限制）；`--previous-zip` 生成增量包，差集按 posix `关键词/商品标题` 比较，不重发已交付商品。

`--root path` 与 `--root=path` 均支持。旧批次状态可显式用 `--state-dir=<旧状态目录>`；素材脚本对应设置任务级 `JD_COLLECTOR_STATE_DIR`。迁移不覆盖已有商品包、示例、源表格或价格证据。

## 整批驱动（scripts/batch_driver/）

大批量用有界驱动链自动跑完整个授权范围，全部能力来自上面各脚本：

- 启动：`JD_BATCH_STATE_DIR=<状态目录> python -X utf8 scripts/batch_driver/start_new_batch.py`。速度环境变量：`JD_BATCH_MAX_REQUESTS`（≤60，建议 45，单页约 50 次后易报浏览器命令异常）、`JD_BATCH_INTERVAL_MS`/`JD_COLLECTOR_MIN_INTERVAL_MS`（下限 50）、`JD_BATCH_ROUND_COOLDOWN_SECONDS`、`JD_COLLECTOR_NAV_MIN_MS`（可降到 500）；`JD_BATCH_ORIGINAL_PRICE_FALLBACK=1` 打开打包/验收的原价兜底链，`JD_BATCH_STAGE_EVERY` 控制中途打包频率。首次启动的节奏参数会持久化到状态目录 `pacing.json`，断点恢复入口无需重复导出环境变量，不会再回落到慢速默认；环境变量仍可显式覆盖并更新该文件。平台频控/验证一旦出现仍立即停。
- 恢复入口按停止原因分流：本地传输瞬断 `resume_after_local_recovery.py`；验证/频控走 keeper 冷却；运营者隔离停摆商品后 `resume_after_stall_isolated.py`；环境退化停止（BLOCKED_ENVIRONMENT）修复内存/守护进程后同样用 `resume_after_stall_isolated.py` 继续；另有 platform_cooldown / verification / abrupt_runner / material_recovery / pacing_change 各入口。
- 同一商品/SKU 连续 3 次瞬态停摆（含本地传输错误、任务页状态漂移）视为确定性商品失败：驱动器自动写入 `errors/` 失败清单（failureType=STALL_原因）并继续整批，不再拦停整个范围；平台级原因（验证、频控、登录）仍然立即停止。护栏：若连续 3 次隔离之间没有任何一轮正常推进（浏览器环境整体退化，如内存不足导致扩展掉线），驱动器停止为 `BLOCKED_ENVIRONMENT` 而不是继续隔离商品，修复环境后由运营者确认继续。
- 页面状态类失败（如 `MAIN_IMAGES_MISSING`）同样走三振隔离：实测多为瞬态、直连重试可过，所以用短冷却（`JD_BATCH_PAGE_STATE_COOLDOWN_SECONDS`，默认 5 秒，持久化进 `pacing.json`）快速重试；同一商品连续 3 次仍失败才隔离进失败清单，不再拦停整批。
- `monitor_batch.ps1 -Stage <状态目录> -Minutes N` 做后台轮询监控。
- 跨批同源商品重建：`prior_receipts.py` 索引旧批回执，同 pid 旧包移入本批备份后按当前数据重建；无法证明归属的同名目录仍然硬失败。

## 店铺在售 SKU 数采集（scripts/shop_sku_count.mjs）

按店铺维度统计在售 SKU 数：店铺前台分页取全部商品，再逐个商品取原生 SKU 矩阵求和。用于运营表「在售SKU」列补齐、店铺选品评估；不采集价格与素材。

- 单店直跑：`node scripts/shop_sku_count.mjs --state-dir <含 browser_context.json 的状态目录> --shops "60407178,230456174" --output <结果.json> [--workers 3] [--chunk 60]`
- 表格驱动（推荐）：`python -X utf8 scripts/batch_driver/shop_sku_driver.py --input <运营表.xlsx> --state-dir <状态目录>`。自动读表格「店铺」列（店铺 ID 或店铺主页链接；纯店铺名无法解析的写入 `shop_table_audit.json`，不猜测），分批调用采集脚本断点续跑，完成后输出 `<表名>_SKU结果_日期.xlsx` 副本并追加「在售SKU数/在售商品数/待补商品数/店铺采集时间」列；原表永不修改。平台原因（验证/频控/登录）立即停为 `BLOCKED_PLATFORM`；同一块连续失败 3 次停为 `BLOCKED_UNKNOWN` 留待人工检查。
- 结果 JSON：每店 `productCount` / `skuCount` / `missing`（未取到 SKU 数的商品），按商品增量落盘，中断后同参数重跑即断点续跑。
- 前台分页上限：翻页耗尽仍少于接口返回总数时标记 `pagingCapExceeded`，并按响应中的分类列表逐分类分片枚举（`shards` 记录每分类商品数、`shardDuplicates` 记录跨片重复），合并去重后仍不足才置 `incomplete=true`；响应无分类可用时记 `note=PAGING_CAP_EXCEEDED`，绝不静默低估。
- 机制与实测（2026-11-25，31 个厨具店、21,621 个商品）：店铺页本身没有 PSign SDK，`whx_searchWare` 必须从 `item.jd.com` 商品页上下文签名调用；`pageSize` 上限 30（更大返回「pageSize过大！」）；前台显示封顶 1000 个商品，但分页接口返回真实总数（实测 1058/1481 等）；单商品 SKU 数取 `colorSizeVO` 矩阵按钮数（单 SKU 商品计 1）。
- 速度：页面内批量签名查询约 0.25 秒/商品，3 个并行页约 800 商品/分钟；5 个并行页会出现浏览器命令丢失，保持 3 个。
- 空店返回 0 个商品，计 0；`missing` 非空时该店 skuCount 为已取到部分之和，需重跑补齐。
- 黄金眼「店铺明细（新）」的 OnSkuNum 是同一口径的内部权威值，但受部门授权限制；本脚本适用于无该部门权限的店铺。

## 素材库批量采集（scripts/collect_materials.mjs）

只采主图/详情图/SKU图，不取价；整批复用**同一个标签页**，避免每商品开关页占用内存。

- 用法：`node scripts/collect_materials.mjs --state-dir <含 browser_context.json 的状态目录> --ids-file <ids.json> --output <materials.jsonl> [--batch 20] [--interval-ms 100]`
- `ids` 文件支持 JSON 数组、`{类目:[id]}` 对象或每行一个 ID；输出 JSONL 每行一个商品（title/spu/crumbs/carousel/colorSize/videos），可断点续跑。
- 机制：打开一个商品页拿到原生签名上下文，页内批量调用 `pc_detailpage_wareBusiness`（默认 20 个/批），整批只用一个标签页，结束统一关闭；单个失败记录 reason 继续，平台验证/频控立即停。
- 实测：902 个商品元数据约 3.5 分钟（约 4 条/秒），全程 1 个标签页。
- 主图下载必须用 `n12`（800×800 无水印）；`n0` 带 `JD.COM` 水印，不要用于素材库。

## 吞吐与稳定性

- 任务页整轮复用：一轮一个新标签页，替代「每个商品一个新页」，既有回归测试锁定。
- 页内批量取价 10 SKU/次；单轮上限 45 次请求可避开单页约 50 次后的浏览器命令异常。
- 素材 CDN 下载已在进程内固定 IPv4（单图 40 秒 → 0.3 秒）；详情图只有域名/目录的坏链按死链丢弃。
- 主图尺寸变体损坏时自动换同图床 `/n12/` 标准变体重试一次，替换记录写入打包回执与暂存 manifest 的 `sourceNotes`（originalUrl/variantUrl/原因）；无变体或变体也失败仍按坏链处理，不跨图床、不静默换图。
- 登录态降级会让整批退化成原价兜底，必须做价格复核，流程见 `references/throughput-and-stability.md`。

## 到手价和顺序

- 优先未划线的 `warePriceGatherVO.priceItemList` 的 `priceType=finalPrice`；无该项才用 `bestPromotion.purchasePrice`。不以 `price.p`、普通 `jdPrice`、历史价或券额推算补缺。
- 响应必须已登录，且请求 SKU 与返回 SKU 完全一致。HTTP 200 但无优惠价记 `ARRIVAL_PRICE_PENDING`；不是接口失败或商品下架。
- 原价兜底仅限用户对该批明确授权：`package_live.py --allow-original-price-fallback` 把授权标记和日期写入状态目录 `price_fallback.json`，打包与验收按 `original_price_user_authorized_日期` 逐 SKU 记录，上架清单列出用原价 SKU 数。无授权时缺价永远保持待补，不打包。
- 前台维度与按钮 `no` 排序；双维度取真实 SKU 交集，禁止笛卡尔积。商品级字段只在排序后首行；见 `references/price-and-sku-contract.md`。

## 保护与验收

- 接口/点击共用独占锁。只控制任务页，保留工作浏览器。未知响应先中止、读回，不自动重放。
- 403/429/PC 频控页/验证/登录失效停本轮；正常人工验证后重新核实状态。没有固定冷却必恢复或内网必放行保证。
- 30 秒请求、60 秒商品页是本地保护初值，不是平台安全承诺。优先减少重复调用，不能为速度牺牲真实到手价和完整 SKU。
- 完整清单须每项状态明确。`DATA_COMPLETE` 仅表示采集数据齐，最终完成必须所有素材包独立 `VERIFIED`；失败/缺价不算成功。
- 验收报告区分 `MAIN_PENDING`（未取得可信主数据/规格矩阵）、`PRICE_PENDING`（矩阵已知但有 SKU 缺到手价）、`PACKAGING_PENDING`（价格齐但尚无完整包回执）；不会将素材暂存或价格齐冒充 `VERIFIED`。
- 本机曾验收 2 商品/35 SKU、81 JPEG/1 MP4；不是154条全批或同事电脑的验收。

## 测试

`node --test tests/*.mjs`

`python -X utf8 -m unittest discover -s tests -p test_*.py -v`

测试包含实际 CLI 离线跑两商品、页面头/同源上下文、SKU对象契约、捕获时序、JPEG编码、工作簿回读和共享锁。常用脚本不得用 import 作为语法测试，使用 `node --check` / Python编译；顶层CLI import可能真正启动采集。

### 离线交付与运营表回填

准备、逐 SKU 断点、独立验证和部分交付可用既有任务目录连续执行。`deliver_batch.py` 的回执包含目标总数、已核验数、本次交付商品、增量排除条目、仍缺的商品及其状态。可售规格缺价继续待补，平台明确下架的规格保留下架证据。只有本批已有明确原价备用授权才可使用 `package_live.py --allow-original-price-fallback`，批驱动不能沿用其他批次的同意。

已持有经授权的店级统计 JSON 时，用 `python scripts/shop_table.py --root <输出目录> --input <运营表.xlsx> --results <统计.json>` 按店铺 ID 写回副本并回读；未解析的名称、无有效统计或仍待补的店铺分别保留证据。仅需清点待核店铺时省略 `--results`。这两个入口都可离线运行。
