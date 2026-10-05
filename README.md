# iPhone Duo 抢购助手（Apple 官网专版）

个人自用的抢购辅助脚本：**只盯 Apple 官网**（用户已确认不抢京东/淘宝，
京东模块代码保留在 `jd/` 但默认关闭）。
到点自动走完选购→加袋→结算流程，**默认停在"核对订单信息"页，由你手动点最后的提交/付款**。

## 先说清楚：它能做什么，不能做什么

**能做：**
- 提前监控 Apple 官网的库存状态，有货立刻推送到你手机（Bark / Server酱）
- 预购开启瞬间（10 月 16 日 20:00）自动完成：选配置 → 加购物袋 → 走完结账流程
- 每一步截图留证，异常时停下并通知你手动接管

**不能做（别指望）：**
- ❌ 0.001 秒下单——物理上不可能。手机到苹果服务器的网络往返就要几十毫秒，
  加上 TLS 握手和反爬验证，一个请求再快也要几百毫秒。脚本的价值是
  "第一时间发现 + 最短路径下单"，不是压毫秒。
- ❌ 绕过验证码、伪装浏览器指纹、多账号并发刷单——本脚本不做这些，
  做了会被苹果/京东风控砍单甚至封号。
- ❌ 保证抢到。首批货源紧张（组装良率据报道约 60%，2026 年全球预计 600 万台），
  脚本提高的是你的"起跑反应"，不是"必中"。

## 关键事实（2026-10-05 已核验）

| 项目 | 内容 |
|---|---|
| 预购开启 | 2026-10-16 20:00（北京时间）|
| 正式发售 | 2026-10-23 |
| 国行价格 | 256GB ¥15999 / 512GB ¥17999 / 1TB ¥21499 / 2TB ¥26499 |
| 颜色 | 星空黑 / 星空白 |
| SIM | 仅 eSIM，无实体卡槽（需提前准备 eSIM 开通）|
| 官方加速通道 | Apple "Get Ready" 预配置流程：美国区约 10 月 12 日开放（提前选配置+付款，到点一键下单）；国行页面截至 9/30 未显示该通道，以 apple.com/cn 实际页面为准 |

## 安装

```bash
cd ~/workspace/iphone-duo-rush
pip install -r requirements.txt
python -m playwright install chromium   # 只需一次；macOS / Linux 通用
cp config.example.yaml config.yaml
```

`config.yaml` 已加入 `.gitignore`，推送 key 只存在你本地。

## 配置（`config.yaml`）

| 字段 | 说明 |
|---|---|
| `drop_time` | 预购时间，默认 `"2026-10-16 20:00:00 +08:00"` |
| `auto_submit` | 默认 `false`。为 `true` 时脚本会自动提交订单并扣款——**除非你非常确定，否则别开** |
| `channels.apple.part_number` | 形如 `MYxxxCH/A`。**10 月 12 日前尚未公布**，公布后到 apple.com/cn 的 Duo 商品页查看源代码，用正则 `[A-Z0-9]{5}CH/A` 搜出你配置（存储/颜色）对应的编号填入 |
| `channels.apple.quantity` | 购买数量，默认 `2`（苹果官网每人限购 2 台）|
| `channels.apple.fulfillment` | `pickup`=到店自提（默认）/ `delivery`=送货上门 |
| `channels.apple.pickup_stores` | 自提门店列表，按顺序尝试（默认 `珠江新城` → `天环广场`，哪个有货选哪个）|
| `channels.apple.pickup_date` | 自提日期，默认 `10月23日`（发售日当天，星期五）|
| `channels.apple.location_zip` | 邮编，用于查附近门店自提库存（广州示例 `510000`）|
| `channels.jd.sku_id` | 京东商品页 URL 里 `sku=` 后面的数字。**预约页上线后填入** |
| `channels.jd.area_id` | 地区 ID，广州示例 `1_72_2799_0` |
| `notify.bark_key` / `notify.server_chan_key` | 二选一或都填；都留空则通知只打印到控制台（抢购时你必须盯着屏幕）|

```bash
python run.py check-config   # 校验配置，会明确告诉你缺了什么
```

## 使用流程

```bash
# 1. 登录（各做一次，会话持久化在 sessions/，密码只进官网）
python run.py login --channel apple   # 手动登录 Apple ID（含 2FA）
python run.py login --channel jd      # 京东 App 扫码登录

# 2. 库存监控（10 月 12 日起可挂着）
python run.py monitor                 # 双渠道循环监控，有货推送
python run.py monitor --once          # 只查一次（调试用）

# 3. 抢购（10 月 16 日 19:55 启动）
python run.py rush --channel both --dry-run   # 先演练：只打开页面校验定位器
python run.py rush --channel both              # 实战：到点自动走单
```

**持续放货判定（DING果式逻辑）：** Apple 监控对每个配置独立计数——
第 1 次查到有货只发普通提醒（一闪而过的库存很常见）；
**连续 3 轮都查到有货**才升级为"持续放货"强提醒，这才是值得立刻下单的真机会。
收到强提醒时如果辅助下单脚本没在跑，手动打开 Apple Store App 下单。

## 验证状态（截至 2026-10-05，诚实记录）

- ✅ 配置校验：`run.py check-config` 对占位配置正确报出警告（exit 1）
- ✅ 解析逻辑：Apple fulfillment / JD stock（含 JSONP 包裹）的解析函数用仿真数据通过测试
- ✅ 计时/通知：drop_time 解析、到点等待循环、Bark/Server酱无 key 降级均测试通过
- ✅ 代码编译：全部 8 个 Python 文件 `py_compile` 通过
- ⚠️ Apple fulfillment API 实测：从本机（云端 IP）请求被苹果边缘节点拦截
  （HTTP 541 + "Page Not Found" 页面）——这是苹果反爬对机房 IP 的常规拦截，
  不是参数错误。接口格式经多方社区脚本验证（见 `apple/monitor.py` 注释）。
  **10 月 12 日后请在你自己的 Mac（广州 residential IP）上跑
  `python run.py monitor --once --channel apple` 做一次真实验证。**
- ⏳ JD stock API 实测：解析逻辑已验证，但缺一个当前在售商品的真实 skuId
  （纯文本搜索拿不到），复制到 sku 后跑 `python run.py monitor --once --channel jd` 验证。
- ⏳ 下单流程：Playwright 脚本内置 `--dry-run` 定位器自检，但 Duo 商品页
  10 月 12 日前不存在，届时务必先 dry-run 再实战。
- iPhone Duo 的 Apple part_number（`…CH/A`）和京东 skuId 截至今日均未公布，
  配置中留的是占位符，按「10 月 12 日清单」填入。

## 时间线清单

**10 月 12 日（约）：**
- [ ] 在 Apple Store App / 官网完成 "Get Ready" 预配置（选存储/颜色/AppleCare+/付款方式）
- [ ] 到 apple.com/cn Duo 商品页找到你的 `part_number`（搜 `CH/A`），填入 `config.yaml`
- [ ] 跑 `python run.py rush --channel apple --dry-run` 校验页面定位器，按报告微调
- [ ] `python run.py check-config` 确认无 ERROR
- [ ] 开通 eSIM（Duo 无实体卡槽；联通已试点线上办理）

**10 月 16 日：**
- [ ] 19:30 前：电脑时钟确认自动同步（系统设置 → 日期与时间 → 自动）
- [ ] 19:55：启动 `python run.py rush --channel both`，浏览器预热，脚本会在 20:00 整自动开跑
- [ ] 20:00：脚本走到订单确认页 → 手机收到推送 → 你检查配置/地址/金额 → 手动点提交订单

## 风险提示

- ⚠️ **苹果官方明确反对抢购软件**：Apple 客服已确认官网有风控 + 限购机制，
  脚本化的下单尝试可能在支付环节被拦截。本脚本默认只自动走到"订单确认页"、
  最后一步由你手动完成——这正是对抗风控的最稳做法；`auto_submit` 风险自负。
- 参考先例：iPhone 18 Pro 在京东预约超 700 万人，首批不到 1 分钟售罄——
  对 Duo 要有"抢不到"的心理预期，脚本提高的是起跑反应，不是必中。
- Apple ID 在新设备登录可能触发 2FA / 短信验证——**提前在常用设备上登录好**，别等到 19:59。
- 京东对高频请求限流：本脚本只做"到点点一次"的拟人操作，不要自己改短轮询间隔去刷。
- 首批溢价与黄牛：按需购买；Apple 官网支持 14 天无理由退货。
- 维修成本：内屏+铰链一体化总成，保外维修预估约 ¥7999；AppleCare+ 两年 ¥2599，建议一并考虑。

## 项目结构

```
run.py                 # CLI 入口
config.example.yaml    # 配置模板
common/notify.py       # Bark + Server酱推送（无 key 时只打印）
common/timing.py       # 到点等待（依赖系统时钟，务必开 NTP 自动同步）
apple/monitor.py       # 轮询苹果 fulfillment API 查门店自提/配送库存
apple/checkout.py      # Playwright：选配置→加袋→结账→停在订单确认页
jd/monitor.py          # 轮询京东 c0.3.cn/stock 查库存状态
jd/rush.py             # Playwright：抢购按钮→购物车→结算→停在订单确认页
sessions/              # 登录态（gitignore，不提交）
screenshots/           # 每步截图（gitignore，不提交）
```
