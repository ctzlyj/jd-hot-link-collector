# 到手价与SKU顺序契约

## 到手价

- 优先：`warePriceGatherVO.priceItemList` 中 `priceType="finalPrice"` 且 `hitLine` 非真的 `price`（当前前台真实展示价）。
- 回退：`bestPromotion.purchasePrice`（旧响应无上述字段时）。
- 禁止：普通 `jdPrice`、`price.p` 原价、清单历史到手价、券面额推算。缺价即 `ARRIVAL_PRICE_PENDING`，不打包、不补齐。
- 唯一例外是用户对本批明确授权的原价兜底：`package_live.py --allow-original-price-fallback` 记录 `price_fallback.json` 后，缺促销价 SKU 才用 `price.p` 原价，`priceSources` 逐 SKU 标记 `original_price_user_authorized_日期`；验收与上架清单按该标记复核，授权随批次状态目录保存，不跨批生效。
- 响应必须 `isLogin===true` 且 `pageConfigVO.skuid` 与请求SKU完全一致，否则按无效处理。

## SKU顺序与矩阵

- 顺序：`colorSizeVO.colorSizeList` 各维度按 `buttons[].no` 升序；`no` 缺失视为前端顺序证据缺失，报错而不是猜测。
- 矩阵：双维度只取真实 `skuList` 交集；组合歧义、重复或矩阵不完整立即报错；禁止笛卡尔积推测。
- 商品级字段只在首行；后续SKU行仅规格与价格库存。

## 表格

22列表头与示例列顺序固定：`*标题, 货号, 商品属性, 类目, 品牌, 规格1, 规格2, *价格, 库存, 短标题, 商家SKU, SKU商品条形码, SKU属性, 无理由退货, 支付方式限制, 产地, 发货地, 商品条形码, 商品毛重(公斤), [包装]长(mm), [包装]宽(mm), [包装]高(mm)`。未知字段留空，不编造商家SKU/条形码；库存固定999。
