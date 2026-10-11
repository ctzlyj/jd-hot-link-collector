# 任务页与会话配置

采集只在已登录账号授权范围内进行；不绑定用户工作页，不导出Cookie/Token/签名，不复制登录资料。

## browser_context.json

写入 `<root>/.collector_state/browser_context.json`：

```json
{
  "session": "<任务页所在浏览器会话名>",
  "tab": "<32位十六进制 targetId>",
  "idleTimeout": 86400,
  "windowMode": "background",
  "probeSku": "<当前正常商品页上的一个商品SKU>",
  "wcli": {
    "main": "<WebCLI入口JS绝对路径，如 D:/tools/webcli/dist/src/main.js>",
    "preload": "<本机WebCLI运行时preload脚本绝对路径>",
    "page": "<WebCLI Page模块绝对路径，如 .../dist/src/browser/page.js>"
  }
}
```

- `tab`：任务页的targetId（32位HEX）。每次新建/被释放后必须更新。
- `idleTimeout`：浏览器租约秒数，必须覆盖最长冷却等待（≥7200）。默认交互租约可能只有600秒，等待15分钟会导致任务页被释放、原tab失效。
- `windowMode` 固定 `background`，不抢占用户焦点。
- `probeSku`：恢复探测用的SKU，必须来自当前正常商品页且已可访问；不要用未验证的商品。
- `wcli`：本机WebCLI三个JS模块的绝对路径；脚本用 `pathToFileURL` 动态加载，不写死安装位置。

## 建页规则

- 复用已验证的登录浏览器会话，新建任务专属商品页；不导航用户当前活动标签。
- 页面自身的官方签名SDK（`PSign`/`SHA256`/`getJsToken`）只在页面内存中使用；脚本仅复用页面上下文，不实现签名。
- 任务页加载正常商品后，才允许启动采集；页面跳频控页/验证页时所有脚本自动熔断。
