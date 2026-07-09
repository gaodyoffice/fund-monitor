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
│   └── index.html         # 前端页面（响应式、PWA）
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
      "gsz": 1.8610, "dwjz": 1.8520, "gztime": "2026-07-09 14:45",
      "pct": 0.49, "has_data": true, "has_pos": true,
      "total_paid": 4000.00, "cur_val": 4019.60,
      "profit": 19.60, "today_profit": 19.42,
      "periods": { "w1": 1.2, "w2": 2.1, "m1": 3.5, "m3": null, "y1": null, "sinceAdd": 5.8 }
    }
  ],
  "summary": {
    "total_cost": 4000.00, "total_value": 4019.60,
    "total_profit": 19.60, "total_today": 19.42, "total_pct": 0.49
  },
  "groups_profit": { "tech": 19.60 },
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
| `records` | array | 是 | 每日涨跌幅记录 |

### records 字段

```json
"records": [
  { "d": "2026-07-08", "v": 1.2 },
  { "d": "2026-07-09", "v": -0.5 }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `d` | string | 日期 (YYYY-MM-DD)，按日期去重 |
| `v` | number | 当日涨跌幅（百分数），+1.2 表示 +1.2% |

---

## 计算逻辑

### 数据来源

```
gsz    = 天天基金 API → 实时估算净值（今日净值/实时估值）
dwjz   = 天天基金 API → 最新公布净值（昨日净值）
jzrq   = 天天基金 API → dwjz 对应的日期
```

### 用户输入

```
cost   = 买入单价（元/份），0 表示无持仓
shares = 持有份额（份），0 表示无持仓
```

### 每个基金的行内计算

```
总投入     = cost 单价 × shares 份额
估算市值   = shares 份额 × gsz 实时估值
浮动盈亏   = 估算市值 − 总投入 = shares 份额 × (gsz 实时估值 − cost 单价)
今日盈亏   = shares 份额 × (gsz 实时估值 − dwjz 昨日净值)，若 dwjz ≤ 0 则返回 0
涨跌幅     = (gsz 实时估值 − dwjz 昨日净值) / dwjz 昨日净值 × 100%，需 dwjz > 0
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
| 成本 | 总投入 | `cost 单价 × shares 份额` | 有持仓显示 ¥，否则 — |
| 份额 | 份额 | 用户录入 | 有持仓显示，否则 — |
| 昨日净值 | dwjz | API 返回 | 有数据时显示 4 位小数，否则 — |
| 实时估值 | gsz | API 返回 | 有数据时显示 4 位小数，红涨绿跌 |
| 涨跌幅 | 涨跌幅 | `(gsz − dwjz) / dwjz × 100%` | 有数据时显示 ±%，红涨绿跌 |
| 周涨幅 | records 求和 | 最近 7 天的 records.v 之和 | 有记录时显示 ±%，红涨绿跌 |
| 2周涨幅 | records 求和 | 最近 14 天的 records.v 之和 | 同上 |
| 月涨幅 | records 求和 | 最近 30 天的 records.v 之和 | 同上 |
| 3月涨幅 | records 求和 | 最近 90 天的 records.v 之和 | 同上 |
| 年涨幅 | records 求和 | 最近 365 天的 records.v 之和 | 同上 |
| 累计涨幅 | records 求和 | 全部 records.v 之和 | 同上 |
| 浮动盈亏 | 浮动盈亏 | `shares 份额 × (gsz 实时估值 − cost 单价)` | 有持仓显示 ±¥，红涨绿跌 |
| 今日盈亏 | 今日盈亏 | `shares 份额 × (gsz 实时估值 − dwjz 昨日净值)`，dwjz≤0 返回 0 | 有持仓显示 ±¥，红涨绿跌 |
| 估算市值 | 估算市值 | `shares 份额 × gsz 实时估值` | 有持仓显示 ¥，颜色同涨跌幅 |
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

### 今日买进金额

```
今日买进金额 = 用户输入的金额（元）
买入单价     = gsz 实时估值（有数据时）或 dwjz 昨日净值
自动份额     = 今日买进金额 / 买入单价
持仓成本     = 买入单价
```

- 仅当 **未手动填写单价和份额** 时触发自动计算
- 编辑基金时，今日买进金额会累加到 `todayBuy` 字段（仅记录，不参与盈亏计算）
- 编辑时若基金无持仓，也会自动建仓（单价=gsz，份额=金额/gsz）

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
- [x] 摘要卡片：总成本、总市值、总盈亏、今日盈亏、盈亏比
- [x] 基金表格：代码/名称、总成本、份额、净值、估值、涨跌幅、周期涨幅、浮动盈亏、今日盈亏、市值
- [x] 涨跌幅对比图（条形图，自适应最大标签宽度，进度条对齐）
- [x] 持仓分布饼图（仅含有持仓的基金）
- [x] 列宽拖拽 + 列显隐面板
- [x] 导入/导出配置
- [x] 交易时段自动刷新（9:30-15:00），收盘停止
- [x] 多设备同步（同一服务端，增删改实时写 funds.json）
- [x] PWA 支持

---

## 与纯前端版的区别

| 特性 | 纯前端版 (fund-monitor) | Server 版 (fund-server) |
|------|------------------------|------------------------|
| 运行方式 | 静态文件服务器 (npx serve) | Python Flask |
| 数据源 | funds.json (只读) + localStorage | funds.json (读写) |
| 增删改持久化 | 手动导出覆盖文件 | 自动写入 funds.json |
| 多设备同步 | adb 推文件 | 访问同一服务器 |
| 文件协议 | 支持 file:// | 需 HTTP 服务 |
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
