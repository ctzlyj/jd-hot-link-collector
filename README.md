# jd-hot-link-collector

京东商品链接素材采集 Skill。接口优先：每个源商品加载一次自己的页面上下文，同商品 SKU 使用页面官方 SDK + XHR 读取真实到手价，不逐 SKU 翻页。点击仅作正常页面上的备用。只采集，不上架、不改图。

## 安装与更新

克隆本仓库到当前用户的 `.joycode/skills/jd-hot-link-collector`（已有安装在该目录执行 `git pull --ff-only`），安装 `requirements.txt`。需要本机 Python、Node，以及已连接当前授权浏览器的 WebCLI；浏览器适配器路径由助手核对后写配置，不复制别人的登录资料。

## 使用

把清单、输出目录告诉 JoyCode：使用 jd-hot-link-collector 采集，只搬运素材不上架。助手按 SKILL.md 配置任务页、解析清单、运行采集、保存断点并验收。

命令入口（目录可包含空格）：

```text
python -X utf8 scripts/prepare_batch.py --input <清单.xlsx> --root <输出目录>
node scripts/collect_signed.mjs --run --root=<输出目录> --interval-ms=30000 --max-requests=8
python -X utf8 scripts/package_live.py --root=<输出目录>
python -X utf8 scripts/verify_batch.py --root=<输出目录>
```

清单和状态在 `.collector_state`，有效数据同时支持原生响应和接口响应。再次执行只补缺失 SKU。旧状态可显式通过 `--state-dir` 迁移，见 SKILL.md。

## 到手价要求

未划线的 `warePriceGatherVO.finalPrice` 优先，旧响应才取 `bestPromotion.purchasePrice`。只提供普通 `jdPrice` 的商品记为待补价，不能以原价、券额推算或输入历史价补齐。保留前台按钮顺序和真实 SKU 交集。

## 本机验收与限制

2026-10-12 本机两个源商品共35个 SKU 的当前前台 finalPrice 全部取得，生成2个素材包（81张JPEG、1个MP4）并独立验证；再次执行0请求复用缓存。修复了跨商品混用上下文、遗漏页面请求头、捕获时序、SKU字符串/规格对象契约和图片模块缺失导入。

这不是同事电脑或154条全批验收。测试中曾有一轮第10个请求超时，保存断点后更换该商品的新上下文并补齐，不能保证无限速或永不超时。403/429/频控/验证必须停止，不因换工具绕过；超时、缺优惠价和真实平台拒绝分别处理。没有公司内网必放行、账号第2条必挂或固定冷却必恢复的结论。

## 测试

```text
node --test tests/*.mjs
python -X utf8 -m unittest discover -s tests -p test_*.py -v
```

包含实际CLI离线两商品、重复运行0请求、SKU规格对象、页面请求头、XHR中止/超时、网络捕获时序、真实JPEG、表格回读及共用锁测试。不要 import CLI 来检查语法，它可能真的启动采集；使用 `node --check` 和 Python编译。
