# 基金实时看板 (Server 版)

Python Flask 服务端版本。电脑/手机通过局域网访问，增删改实时写入 `funds.json`，多设备数据一致。

---

## 目录

- [快速启动](#快速启动)
- [访问方式](#访问方式)
- [Termux (手机) 后台运行](#termux-手机-后台运行)
- [项目结构](#项目结构)
- [API 文档](#api-文档)
- [数据结构](#数据结构)
- [计算逻辑](#计算逻辑)
- [多设备同步流程](#多设备同步流程)
- [与纯前端版的区别](#与纯前端版的区别)

---

## 快速启动

```bash
cd fund-server
pip install -r requirements.txt
python app.py
```

服务启动在 `http://0.0.0.0:5000`。

---

## 访问方式

| 设备 | 地址 | 说明 |
|------|------|------|
| 本机 | http://localhost:5000 | PC 访问 |
| 局域网 PC | http://192.168.x.x:5000 | 手机或其他 PC 访问 |
| 局域网 手机 | 同上 | 用手机浏览器打开 |

启动日志中会打印本机局域网 IP。

---

## Termux (手机) 后台运行

```bash
# 安装 Python
pkg install python

# 安装依赖
pip install flask

# 进入项目目录
cd /sdcard/fund-server

# 直接后台运行
nohup python app.py > server.log 2>&1 &

# 或用 pm2（推荐）
pm2 start app.py --interpreter python --name fund-server
pm2 save

# 查看日志
pm2 logs fund-server

# 重启
pm2 restart fund-server

# 停止
pm2 stop fund-server
```

---

## 项目结构

```
fund-server/
├── app.py                 # Flask 服务入口
│   ├── GET  /             → 返回 index.html
│   ├── GET  /api/config   → 读取 funds.json 返回配置
│   ├── POST /api/save     → 接收 JSON 写入 funds.json
│   └── POST /api/refresh  → 并发抓取 → 积累 records → 计算 → 返回全量数据
├── funds.json             # 唯一数据源（增删改实时写入）
├── requirements.txt       # flask>=3.0, requests>=2.28
├── templates/
│   └── index.html         # 前端页面（响应式）
└── README.md
```

---

## API 文档

### 服务端 API

#### GET /api/config

读取 `funds.json` 返回完整配置。

**响应示例**：

```json
{
  "groups": [
    { "id": "watchlist", "name": "自选", "color": "#9e9e9e", "watchlist": true },
    { "id": "tech", "name": "科技", "color": "#58a6ff" }
  ],
  "funds": [
    {
      "code": "008702",
      "name": "中欧时代先锋ETF联接A",
      "cost": 1.8520,
      "shares": 2158.58,
      "todayBuy": 0,
      "groupId": "tech",
      "addTime": "2026-07-01",
      "yesterdayProfit": 57.19,
      "records": [
        { "d": "2026-07-08", "v": 1.2 }
      ]
    }
  ]
}
```

#### POST /api/save

接收 JSON body 并写入 `funds.json`。

**请求**：

```
Content-Type: application/json

{
  "groups": [...],
  "funds": [...]
}
```

**响应**：

```json
{ "ok": true }
```

#### POST /api/refresh

并发抓取所有基金的实时数据 → 积累日涨跌幅记录 → 保存 → 返回全量计算数据。

**请求**：无 body

**响应**：

```json
{
  "funds": [
    {
      "code": "008702", "name": "...", "cost": 1.8520, "shares": 2158.58,
      "yesterdayProfit": 57.19,
      "gsz": 1.8610, "dwjz": 1.8520, "gztime": "2026-07-09 14:45",
      "pct": 0.49, "hasData": true, "hasPos": true,
      "totalPaid": 4000.00, "curVal": 4019.60,
      "profit": 19.60, "todayProfit": 19.42, "profitRate": 0.49,
      "periods": { "w1": 1.2, "w2": 2.1, "m1": 3.5, "m3": null, "y1": null, "sinceAdd": 5.8 }
    }
  ],
  "summary": {
    "totalCost": 4000.00, "totalValue": 4019.60,
    "totalProfit": 19.60, "totalToday": 19.42, "totalPct": 0.49
  },
  "groupsProfit": { "tech": { "profit": 19.60, "todayProfit": 19.42, "cost": 4000, "hasLive": true } },
  "groups": [...]
}
```

---

## 数据结构

### funds.json

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | 6 位基金代码 |
| `name` | string | 是 | 基金名称 |
| `cost` | number | 否 | **买入单价**（元/份），0 表示仅观察 |
| `shares` | number | 否 | 持有份额，0 表示仅观察 |
| `todayBuy` | number | 否 | 今日买进金额记录，仅累加不参与计算 |
| `groupId` | string | 是 | 所属分组 ID |
| `addTime` | string | 是 | 添加日期 (YYYY-MM-DD) |
| `yesterdayProfit` | number | 否 | 昨日盈亏金额（盘后由 eastmoney 官方净值计算持久化） |
| `records` | array | 是 | 每日涨跌幅记录 |

### records 字段

```json
"records": [
  { "d": "2026-07-08", "v": 1.2, "p": 50.0, "dwjz": 4.1434 },
  { "d": "2026-07-09", "v": 1.64, "p": 57.19, "dwjz": 4.3854 }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `d` | string | 日期 (YYYY-MM-DD)，按日期去重 |
| `v` | number | 当日涨跌幅（百分数），+1.2 表示 +1.2% |
| `p` | number | 当日盈亏金额，如 57.19 表示 +¥57.19 |
| `dwjz` | number | 当日记录创建时的最新公布净值 |

---

## 计算逻辑

### 数据来源

```
gsz    = 天天基金 API → 实时估算净值（今日净值/实时估值）
        盘后 ≥15:00 被 eastmoney 今日官方净值替换（若已发布）
dwjz   = 天天基金 API → 最新公布净值（昨日净值）
        盘后 ≥15:00 被 eastmoney 上一期官方净值替换（若已发布）
        最新的公布净值 = 昨日净值 = 上一天的官方收盘价
jzrq   = 天天基金 API → dwjz 对应的日期
```

### 用户输入

```
cost   = 买入单价（元/份），0 表示无持仓
shares = 持有份额（份），0 表示无持仓
```

### 每个基金的行内计算

```
总投入       = cost 单价 × shares 份额
估算市值     = shares 份额 × gsz 实时估值
浮动盈亏     = 估算市值 − 总投入 = shares 份额 × (gsz 实时估值 − cost 单价)
今日盈亏     = shares 份额 × (gsz 实时估值 − dwjz 昨日净值)，若 dwjz ≤ 0 则返回 0
昨日盈亏     = shares 份额 × (当前dwjz最新公布净值 − eastmoney返回的上一期净值)
              由 api_refresh 在每次刷新时独立从 eastmoney 获取历史净值计算
              结果持久化到 funds.json 的 yesterdayProfit 字段
涨跌幅       = (gsz 实时估值 − dwjz 昨日净值) / dwjz 昨日净值 × 100%，需 dwjz > 0
持仓收益率   = 浮动盈亏 / 总投入 × 100%（需总投入 > 0）
```

### 总览（摘要卡片）

汇总当前选中分组（或全部）中 `shares > 0` 的基金：

```
总持仓成本   = Σ(cost 单价 × shares 份额)
总估算市值   = Σ(shares 份额 × gsz 实时估值)
总浮动盈亏   = Σ(shares 份额 × (gsz 实时估值 − cost 单价))
总今日盈亏   = Σ(shares 份额 × (gsz 实时估值 − dwjz 昨日净值))，单基金 dwjz≤0 时不纳入
综合收益率   = 总浮动盈亏 / 总持仓成本 × 100%
```

| 总览项 | 显示规则 | 颜色 |
|--------|----------|------|
| 持仓成本 | 有持仓显示金额，否则 — | `#58a6ff` |
| 估算市值 | 有持仓显示金额，否则 — | `#58a6ff` |
| 浮动盈亏 | 有持仓显示 ±¥，否则 — | ≥0 红 / <0 绿 |
| 今日盈亏 | 有持仓显示 ±¥，否则 — | ≥0 红 / <0 绿 |
| 综合收益率 | 有持仓显示 ±%，否则 — | ≥0 红 / <0 绿 |

### 表格列

| 列 | 字段 | 计算方式 | 显示规则 |
|----|------|----------|----------|
| 代码/名称 | — | API 返回 | 始终显示 |
| 总投入 | 总投入 | `cost 单价 × shares 份额` | 有持仓显示 ¥（整数），否则 — |
| 持仓单价 | cost | 用户录入，可由 todayBuy 刷新修正 | 有持仓显示 ¥4 位小数，否则 — |
| 份额 | shares | 用户录入，可由 todayBuy 刷新修正 | 有持仓显示，否则 — |
| 昨日净值 | dwjz | 最新公布净值（fundgz API 或 eastmoney 修正） | 有数据时显示 4 位小数，否则 — |
| 实时估值 | gsz | fundgz API（盘后由 eastmoney 官方净值替换） | 有数据时显示 4 位小数，红涨绿跌 |
| 涨跌幅 | 涨跌幅 | `(gsz − dwjz) / dwjz × 100%` | 有数据时显示 ±%，红涨绿跌 |
| 周涨幅 | records 求和 | 最近 7 天的 records.v 之和 | 有记录时显示 ±%，红涨绿跌 |
| 2周涨幅 | records 求和 | 最近 14 天的 records.v 之和 | 同上 |
| 月涨幅 | records 求和 | 最近 30 天的 records.v 之和 | 同上 |
| 3月涨幅 | records 求和 | 最近 90 天的 records.v 之和 | 同上 |
| 年涨幅 | records 求和 | 最近 365 天的 records.v 之和 | 同上 |
| 累计涨幅 | records 求和 | 全部 records.v 之和 | 同上 |
| 今日盈亏 | 今日盈亏 | `shares 份额 × (gsz − dwjz)`，dwjz≤0 返回 0 | 有持仓显示 ±¥，≥0 红 / <0 绿 |
| 昨日盈亏 | yesterdayProfit | `shares 份额 × (当前dwjz最新净值 − eastmoney上一期净值)`，每次刷新时独立计算并持久化 | 有持仓显示 ±¥，≥0 红 / <0 绿 |
| 浮动盈亏 | 浮动盈亏 | `shares 份额 × (gsz − cost 单价)` | 有持仓显示 ±¥，≥0 红 / <0 绿 |
| 持仓收益率 | 持仓收益率 | `浮动盈亏 / 总投入 × 100%`（需总投入 > 0） | 有持仓显示 ±%，≥0 红 / <0 绿 |
| 估算市值 | 估算市值 | `shares 份额 × gsz` | 有持仓显示 ¥，颜色同涨跌幅 |
| 操作 | 按钮 | 加仓/买进/编辑/删除 | 有持仓显示 ➕，无持仓显示 💰 |

### 分组标签颜色

```
选中分组 → 遍历组内所有基金
  若无实时数据或无持仓 → 跳过
  组总盈亏 += shares 份额 × (gsz 实时估值 − cost 单价)
若总盈亏 > 0  → 标签点变红
若总盈亏 < 0  → 标签点变绿
若总盈亏 = 0  → 标签点恢复原色
```

### 持仓分布饼图

```
仅统计 shares > 0 的基金
总投入 total = Σ(cost 单价 × shares 份额)
每只基金占比 = (cost 单价 × shares 份额) / total × 100%
```

### 今日买进金额 (todayBuy)

**设计目标**：盘中只记金额不记份额，盘后按官方净值统一修正。

```
买入操作（盘前 <15:00）
  不立即计算份额和成本
  只记录 todayBuy += 买入金额
  刷新后（盘后 ≥15:00）自动按官方净值合并到持仓

买入操作（盘后 ≥15:00）
  立即用官方净值计算份额和成本
  不设 todayBuy（数据已准确）

修正流程（api_refresh 内）
  遍历所有基金，若有 todayBuy > 0：
    price = live[code]['gsz']  # 盘后已被 eastmoney 官方净值替换
    add_shares = todayBuy / price
    合并到现有持仓：shares += add_shares，重算加权成本 cost
    todayBuy = 0
```

- 增/买/加仓操作盘中只累加 `todayBuy`，不立即算 cost/shares
- 盘后首次刷新时统一按官方净值修正：追加份额 + 重算加权成本
- `todayBuy` 不参与日常盈亏计算，仅作为"待修正金额"标记

### 盘后官方净值修正 (eastmoney)

```
获取：api_refresh 每次刷新时并发请求 eastmoney 历史净值接口
     pageSize=2 → 返回最近两期官方净值
     records[0]: {DWJZ: 今日净值, FSRQ: 日期}
     records[1]: {DWJZ: 昨日净值, FSRQ: 日期}

昨日盈亏 = 份额 × (最新公布净值 − 上一期官方净值)
          由 eastmoney 返回的 records[0].DWJZ 和 records[1].DWJZ 计算
          持久化到 funds.json 的 yesterdayProfit 字段

gsz 替换（仅 ≥15:00 执行）：
  当 eastmoney 返回的日期 = 今天时：
    gsz  = 今日官方净值（替换 fundgz 的实时估算值）
    dwjz = 昨日官方净值（替换 fundgz 的最新公布值）

注意：
  - 盘中（<15:00）：eastmoney 照常请求仅用于昨日盈亏计算，不影响 gsz
  - 盘后（≥15:00）：eastmoney 数据同时用于 gsz 修正和昨日盈亏持久化
  - 若 eastmoney 返回无昨日净值（仅一期记录），昨日盈亏保持原值不更新
```

### 每日涨跌幅记录

```
记录值 v = (gsz − dwjz) / dwjz × 100
```

- 由后端 `POST /api/refresh` 在每次刷新时检查
- 当天尚未记录时追加（按日期去重）

### 周期涨幅计算

```
周涨幅   = sum(最近 7 天 records.v)
2周涨幅  = sum(最近 14 天 records.v)
月涨幅   = sum(最近 30 天 records.v)
3月涨幅  = sum(最近 90 天 records.v)
年涨幅   = sum(最近 365 天 records.v)
累计涨幅 = sum(全部 records.v)
```

**注意**：算术累加，非复合收益率。`+1% + 2% = 3%`。

### 示例

```
7月8日  添加基金 A，今日买进 1000 元，gsz=1.0734
  → 自动设置 cost 单价=1.0734, shares 份额=931.43
  → 今日盈亏 = 931.43 份 × (1.0734 实时 − dwjz 昨日)

7月9日  今日 gsz=1.0850, dwjz=1.0734
  → 浮动盈亏 = 931.43 × (1.0850 − 1.0734) = +10.80
  → 今日盈亏 = 931.43 × (1.0850 − 1.0734) = +10.80
```

---

## 功能清单

- [x] 分组管理（增删改、标签切换；删除分组同步删除组内基金）
- [x] 基金增删改（6 位代码、可选单价/份额/今日买进金额）
- [x] 自动建仓：今日买进金额 → 实时估值确定单价 → 计算份额
- [x] 实时估值刷新（后端并发抓取，前端单次 POST 获取全量数据；交易时段自动运行）
- [x] 盘后 eastmoney 修正：gsz/dwjz 替换为官方净值，昨日盈亏独立计算
- [x] 摘要卡片：总成本、总市值、总盈亏、今日盈亏、昨日盈亏、盈亏比
- [x] 基金表格：代码/名称、总投入、持仓单价、份额、净值、估值、涨跌幅、周期涨幅、今日盈亏、昨日盈亏、浮动盈亏、持仓收益率、市值
- [x] 涨跌幅对比图（条形图，自适应最大标签宽度，进度条对齐）
- [x] 持仓分布饼图（仅含有持仓的基金）
- [x] 列宽拖拽 + 列显隐面板
- [x] 导入/导出配置
- [x] 自动刷新（盘中/盘后持续），盘中 temp + 刷新后按收盘价修正成本
- [x] 多设备同步（同一服务端，增删改实时写 funds.json）
- [x] 表格排序（降序/升序/取消），图表同步

---

## 与纯前端版的区别

| 特性 | 纯前端版 | Server 版 (本项目) |
|------|---------|-------------------|
| 运行方式 | 静态文件服务器 (npx serve) | Python Flask |
| 数据源 | funds.json (只读) + localStorage | funds.json (读写) |
| 增删改持久化 | 手动导出覆盖文件 | 自动写入 funds.json |
| 多设备同步 | adb 推文件 | 访问同一服务器 |
| 文件协议 | 支持 file:// | 需 HTTP 服务 |
| 盘后修正 | 只依赖 fundgz | eastmoney 官方净值修正 + 昨日盈亏持久化 |
| Termux 运行 | 可以 (npx serve) | 可以 (python app.py) |

---

## 本地开发

```bash
# 克隆
git clone https://github.com/gaodyoffice/fund-monitor.git
cd fund-server

# 安装依赖
pip install -r requirements.txt

# 启动
python app.py

# 开发模式（热重载）
FLASK_ENV=development python app.py
```
