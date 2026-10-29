# Apple Store 库存监听脚本

使用 Python 3.9+，仅依赖标准库，无需 `pip install`，支持 macOS、Linux 和 Windows。不再提供桌面客户端或安装包。

支持 12 个国家或地区：中国大陆、中国香港、中国台湾、新加坡、日本、澳大利亚、马来西亚、美国、加拿大、英国、德国和韩国，均可列出门店、商品目录并监听库存。

每个国家或地区均提供 iPhone 18 Pro、iPhone 18 Pro Max 各 16 个 SKU，iPhone Duo 8 个 SKU。

## 快速使用

保留 `apple_store_helper.py` 和同目录下的 `config/files/` 数据目录。

```sh
# 查看国家或地区
python3 apple_store_helper.py list-areas

# 查看上海门店
python3 apple_store_helper.py list-stores --filter 上海

# 指定国家或地区模糊搜索门店
python3 apple_store_helper.py list-stores --area hk --filter Canton

# 打印全部大陆门店和编号
python3 apple_store_helper.py list-stores

# 打印全部香港门店和编号
python3 apple_store_helper.py list-stores --area hk

# 查看大陆 Duo 型号、颜色、容量和 SKU
python3 apple_store_helper.py list-products --area cn --filter Duo

# 监听环球港门店的星光白色 Duo 256GB，每轮间隔 10 秒
python3 apple_store_helper.py watch --area cn --store R683 --product MK2M4CH/A
```

Windows 可将 `python3` 换成 `py -3`。数据路径相对于脚本位置解析，可在任意工作目录运行脚本。

国家或地区代码：

| 代码 | 国家或地区 | 能力 |
| --- | --- | --- |
| cn | 中国大陆 | 门店、商品目录、库存监听 |
| hk | 中国香港 | 门店、商品目录、库存监听 |
| tw | 中国台湾 | 门店、商品目录、库存监听 |
| sg | 新加坡 | 门店、商品目录、库存监听 |
| jp | 日本 | 门店、商品目录、库存监听 |
| au | 澳大利亚 | 门店、商品目录、库存监听 |
| my | 马来西亚 | 门店、商品目录、库存监听 |
| us | 美国 | 门店、商品目录、库存监听 |
| ca | 加拿大 | 门店、商品目录、库存监听 |
| uk | 英国 | 门店、商品目录、库存监听 |
| de | 德国 | 门店、商品目录、库存监听 |
| kr | 韩国 | 门店、商品目录、库存监听 |

默认 `cn`，也可使用 `zh_CN` 等 locale。英国也支持 `gb`。

## 监听选项

```sh
# 查询一轮后退出
python3 apple_store_helper.py watch --store R683 --product MK2M4CH/A --once

# 监听上海全部门店的全部 Duo 型号
python3 apple_store_helper.py watch --store 上海 --product Duo

# 同时监听指定门店和多个 SKU
python3 apple_store_helper.py watch --area cn --store R683,R705 \
  --product MK2M4CH/A,MK2N4CH/A

# 香港全部门店、全部型号
python3 apple_store_helper.py watch --area hk --product

# 在香港全部门店中筛选 Canton，监听全部型号
python3 apple_store_helper.py watch --area hk --filter Canton --product

# 指定多个门店，不指定型号时默认全部型号
python3 apple_store_helper.py watch --area cn --store R683,R705

# 有货后继续监听，并在出现新的有货状态时打开购物袋
python3 apple_store_helper.py watch --store R683 --product Duo \
  --interval 15 --timeout 10 --keep-watching --open-bag
```

`--store` 和 `--product` 支持编号/SKU 精确匹配，或名称关键词不区分大小写的包含匹配；支持逗号分隔和重复参数，可混用，取并集并自动去重，忽略逗号两侧空格。

省略 `--store` 时选择所选国家或地区的全部门店；`--filter` 在门店选择结果中进一步筛选，不筛选商品。多个 `--filter` 取并集，再与 `--store` 选择结果取交集；无匹配时直接报错，不会发起库存请求。

省略 `--product` 或单独使用不带值的 `--product` 均选择全部型号；任意一个裸 `--product` 也代表全部型号。重复 SKU 只查询一次。启动时会列出完整监听范围，按 `Ctrl+C` 停止。

默认每轮查询完成后等待 10 秒，最低 1 秒；每个请求默认超时 10 秒，最多并发查询 4 家门店。每家门店按最多 20 个 SKU 分批查询，避免大批量查询时响应被截断；部分批次失败时保留其他批次的成功结果。每轮显示有货、无货和未知数量。请求失败、门店缺失、库存字段缺失或格式错误均视为未知，不会当作无货。

默认检测到任意有货后退出；`--keep-watching` 继续运行，只有新出现的有货状态才触发通知。查询失败不会重置之前的有货状态。终端始终输出有货记录和购物袋地址，`--open-bag` 才会自动打开浏览器。

`--once` 的退出码：`0` 检测到有货，`1` 全部无货，`2` 查询存在未知或参数/数据错误；手动中断为 `130`。库存结果只代表查询时刻，不会自动下单。请提前登录 Apple 官网并将商品加入购物袋，收到提醒后手动选择门店并购买。

## Bark 通知（可选）

在 iOS 安装 Bark，复制设备通知地址，通过环境变量传入：

```sh
export BARK_URL='https://api.day.app/你的设备Key'
python3 apple_store_helper.py watch --store R683 --product Duo
```

也支持 `--bark-url`。检测到新增有货状态后，以 JSON POST 发送通知，点击通知可进入对应国家或地区购物袋。Bark 失败会输出提示，库存查询继续按原选项运行；脚本不会记录设备 Key。未配置时仅输出终端提醒。

## 产品数据

机型配置于 2026-10-29 从各国家或地区 Apple 官方购买页面的 `productSelectionData` 提取，包含当地 SKU、颜色和容量：

- [iPhone 18 Pro / Pro Max](https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro)
- [iPhone Duo](https://www.apple.com.cn/shop/buy-iphone/iphone-duo)

日本页面同一 SKU 的不同购买方案已去重。不同国家或地区 SKU 可能不同，请先使用对应国家或地区的 `list-products` 查询。门店和产品数据为本地快照；库存每轮通过 Apple 官方接口实时查询，具体可购买状态以官网为准。

新增国家的数据同样采集于 2026-10-29。新增 SKU 来自各国家 Apple 官方购买页，使用当地 SKU，不推测型号后缀；美国页面同一 SKU 的运营商方案已去重。门店来自 [Apple 官方全球零售店清单](https://www.apple.com/retail/storelist/)，新增美国 269 家、加拿大 28 家、英国 39 家、德国 16 家、韩国 7 家。

库存查询使用各国家或地区的 `/shop/retail/pickup-message`，参数为 `pl=true`、`mts.0=regular`、`store` 和 `parts.N`。从 `body.stores[].partsAvailability[SKU].pickupDisplay` 读取状态：`available` 为有货，`unavailable` / `ineligible` 为当前不可取货，其他值视为未知。

不再使用返回 HTTP 541 的旧 `/shop/fulfillment-messages` 及其 `compact.storeSelectionEnabled` 字段。[原项目的问题报告](https://github.com/hteen/apple-store-helper/issues/131)记录了这次接口迁移。

## 验证

```sh
python3 -m unittest discover -s tests -v
```

测试覆盖国家或地区数据、列表命令与模糊搜索、型号筛选、新旧库存响应、请求编码、分批查询、异常处理和通知去重；自动测试不向 Apple 或 Bark 发送请求。

2026-10-29 迁移后的实际接口验证：7 个国家或地区各选 1 家门店，分别为 `cn/R705`、`hk/R499`、`tw/R694`、`sg/R736`、`jp/R005`、`au/R483`、`my/R742`；各国家或地区全部 40 个 SKU 的响应均成功解析，共 280 项，未知数量为 0。另通过命令行实测 `cn/R683` 的 `MK2M4CH/A`，正确返回无货及退出码 `1`。这些检查证明当时请求和解析可用，不代表所有门店或未来库存，也未验证实际下单。

新增国家的实际接口验证：`us/R225`、`ca/R209`、`uk/R363`、`de/R519`、`kr/R770` 各 40 个 SKU 均成功解析，共 200 项。英国首次查询一批连接被重置，按未知处理；复测全部通过。
