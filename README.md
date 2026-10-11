# jd-hot-link-collector

京东爆品链接批量采集 Skill：把关键词分段的商品清单采集为可审核素材包（真实逐SKU到手价、前台SKU顺序、主图/详情图/SKU图/主图视频、22列商品信息表），带断点续采与平台频控熔断。只采集，不上架。

## 安装

```powershell
git clone https://github.com/ctzlyj/jd-hot-link-collector "$env:USERPROFILE\.joycode\skills\jd-hot-link-collector"
pip install -r "$env:USERPROFILE\.joycode\skills\jd-hot-link-collector\requirements.txt"
```

## 快速开始

```powershell
$skill = "$env:USERPROFILE\.joycode\skills\jd-hot-link-collector"
# 1. 解析清单（无网络请求）
python -X utf8 "$skill\scripts\prepare_batch.py" --input 清单.xlsx --root D:\collection
# 2. 在已登录浏览器建任务页并写 browser_context.json（见 references/browser-session-setup.md）
# 3. 长冷却后先做真实点击测试，再采集
node "$skill\scripts\clean_session_click_test.mjs" --root D:\collection
node "$skill\scripts\collect_signed.mjs" --run --root D:\collection --interval-ms=30000 --max-requests=20
# 4. 打包与验收
python -X utf8 "$skill\scripts\package_live.py" --root D:\collection
python -X utf8 "$skill\scripts\verify_batch.py" --root D:\collection
```

## 测试

```powershell
node --test tests/test_browser_worker.mjs tests/test_request_policy.mjs tests/test_collection_policy.mjs tests/test_task_context.mjs
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

## 边界

- 仅处理已授权链接与素材；不发布、不改图、不报名活动。
- 出现403/429/PC频控页/验证页立即熔断，不换账号、IP或端点绕过；详见 `references/rate-limit-and-recovery.md`。
- 到手价只取当前登录前台真实数据，禁止原价或历史价补齐。
