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

- `tab`：诊断或单页探测的targetId（32位HEX）。接口批量采集会为每个源商品新建自己的任务页，不依赖这个旧tab持续存活。
- `idleTimeout`：浏览器租约秒数，必须覆盖最长冷却等待（≥7200）。默认交互租约可能只有600秒，等待15分钟会导致任务页被释放、原tab失效。
- `windowMode` 固定 `background`，不抢占用户焦点。
- `probeSku`：恢复探测用的SKU，必须来自当前正常商品页且已可访问；不要用未验证的商品。
- `wcli`：本机WebCLI三个JS模块的绝对路径；脚本用 `pathToFileURL` 动态加载，不写死安装位置。

## 建页规则

- 复用已验证的登录浏览器会话，新建任务专属商品页；不导航用户当前活动标签。
- 页面自身的官方签名SDK（`PSign`/`SHA256`/`getJsToken`）只在页面内存中使用；脚本仅复用页面上下文，不实现签名。
- 任务页加载正常商品后，才允许启动采集；页面跳频控页/验证页时所有脚本自动熔断。
- `collect_signed.mjs` 会先新建空任务页，开启捕获，再导航到源商品，等待原生响应完成。随后在页面内存保留所需请求头、签名上下文及该商品真实SKU白名单。不得把一个商品页的上下文用于其他商品。
- 页面 URL 的 `pcdk/sdx/soaRate`（若存在）和原生请求的 `X-Skuid-Param/x-sdx/soaRate` 只在浏览器内存中使用，不写到此配置或任何日志。
