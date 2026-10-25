---
name: jd-hot-link-collector
description: 将京东商品链接清单采集为关键词/商品标题命名的素材包，接口优先按每个源商品的原生上下文读取逐SKU真实到手价和前台SKU顺序，提供点击备用、主图/详情图/SKU图/主图视频、22列商品信息表、断点恢复及独立验收。用户要求采集或搬运素材但不上架时使用；不发布、不修图、不绕过平台登录或风控。
riskLevel: RL3
---

# 京东链接素材采集

只采集，不上架、不改图。先读 `references/browser-session-setup.md`；涉及浏览器先读本机 `browser-task-router` 并复用当前授权连接。用户只需提供清单/链接和输出目录，由助手配置本机依赖、任务会话与流程，不要求用户手写程序。

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

- 启动：`JD_BATCH_STATE_DIR=<状态目录> python -X utf8 scripts/batch_driver/start_new_batch.py`。速度环境变量：`JD_BATCH_MAX_REQUESTS`（≤60，建议 45，单页约 50 次后易报浏览器命令异常）、`JD_BATCH_INTERVAL_MS`/`JD_COLLECTOR_MIN_INTERVAL_MS`（下限 50）、`JD_BATCH_ROUND_COOLDOWN_SECONDS`、`JD_COLLECTOR_NAV_MIN_MS`（可降到 500）；`JD_BATCH_ORIGINAL_PRICE_FALLBACK=1` 打开打包/验收的原价兜底链，`JD_BATCH_STAGE_EVERY` 控制中途打包频率。平台频控/验证一旦出现仍立即停。
- 恢复入口按停止原因分流：本地传输瞬断 `resume_after_local_recovery.py`；验证/频控走 keeper 冷却；运营者隔离停摆商品后 `resume_after_stall_isolated.py`；另有 platform_cooldown / verification / abrupt_runner / material_recovery / pacing_change 各入口。
- 同一商品/SKU 连续 3 次瞬态停摆视为确定性商品失败：驱动器自动写入 `errors/` 失败清单（failureType=STALL_原因）并继续整批，不再拦停整个范围；平台级原因（验证、频控、登录）仍然立即停止。
- `monitor_batch.ps1 -Stage <状态目录> -Minutes N` 做后台轮询监控。
- 跨批同源商品重建：`prior_receipts.py` 索引旧批回执，同 pid 旧包移入本批备份后按当前数据重建；无法证明归属的同名目录仍然硬失败。

## 吞吐与稳定性

- 任务页整轮复用：一轮一个新标签页，替代「每个商品一个新页」，既有回归测试锁定。
- 页内批量取价 10 SKU/次；单轮上限 45 次请求可避开单页约 50 次后的浏览器命令异常。
- 素材 CDN 下载已在进程内固定 IPv4（单图 40 秒 → 0.3 秒）；详情图只有域名/目录的坏链按死链丢弃。
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
