# TODO

## 1. 刷新后保持当前分组

**问题**: 聚焦某个分组时点击刷新，数据显示全部基金而非当前分组。

**原因**: `app.py` `/api/refresh` 硬编码 `'all'` 传入 `compute_funds`。

**改动**:
- 后端: 从请求体读取 `curGroup` 参数，传入 `compute_funds(funds, live, groups, cur_group)`
- 前端: `fetchAllFunds()` 发送 `{ curGroup }` 到 `/api/refresh`

```python
# app.py
data = request.get_json(silent=True) or {}
cur_group = data.get('curGroup', 'all')
# ...
result = compute_funds(funds, live, groups, cur_group)
```

```javascript
// index.html fetchAllFunds()
const resp = await fetch('/api/refresh', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ curGroup: curGroup })
});
```

---

## 2. 盘后定时刷新自动用官方净值修正

**问题**: 实时估值仅盘中有效，盘后应尝试获取官方最新净值替代。

**现状**: `app.py` `/api/refresh` 已有 `fetch_official_nav()` + 替换 `live[code]['gsz']` 逻辑。需确认：
- 定时刷新时总是尝试获取官方净值
- 当 eastmoney 返回的 `FSRQ == today` 时才采用（避免拿错日期）
- 获取失败则保留 fundgz 的实时估值不变

**无需大改**，确认逻辑正确即可。

---

## 3. 当日买入统一记录，盘后统一修正

**问题**: `confirmBuy`/`confirmAddPosition` 中 `isAfterMarket` 分支导致盘后买入不设 `todayBuy`，`/api/refresh` 的修正逻辑（`todayBuy > 0`）跳过它们。

**改动**: 去掉 `isAfterMarket` 判断，所有买入/加仓都设 `todayBuy`，由 `/api/refresh` 统一修正。

```javascript
// confirmBuy / confirmAddPosition
f.cost = price;
f.shares = cost / price;
f.todayBuy = (f.todayBuy || 0) + cost;  // always set
```

同时统一 toast 提示（不再区分盘中/盘后）：

```javascript
showToast(`${f.name} ¥${cost.toFixed(2)} 已记录，刷新后以官方净值修正`);
```
