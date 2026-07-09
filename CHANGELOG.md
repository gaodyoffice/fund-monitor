## v1.1 (2026-07-09)

### 新增
- 全部 tab：只显示有持仓基金，同代码跨组合并（累加份额+加权均价）
- 表格新增"持仓收益"列（= 浮动盈亏 / 总投入 × 100%）
- 分组标签颜色改为根据当日盈亏（红涨绿跌）

### 优化
- 添加/编辑/买进/加仓/删除均改为单只刷新（`refreshOne`），不再全量刷新，操作瞬间完成
- `saveFunds`/`saveGroups` 改为返回 Promise，所有 CRUD 路径 await 后执行后续操作，消除时序竞争
- 删除基金只清理不再被任何分组使用的 `fetched` 缓存
- 总投入改为整数显示

### 修复
- 添加基金时全量刷新（15只基金）耗时过长导致用户误以为失败
- `saveFunds` 未 await 导致 POST /api/save 与 POST /api/refresh 时序竞争，删除的基金被写回

## v1.0 (2026-07-09)

### 新增
- 后端 `POST /api/refresh`：并发抓取所有基金实时数据 → 积累日涨跌幅记录 → 计算全量衍生字段 → 返回渲染数据
- `compute_funds()` 统一后端计算：每只基金 gsz/dwjz/pct/profit/todayProfit/periods/total_paid/cur_val
- 表格新增"单价"列，原"成本"改名为"总投入"
- 列显隐面板支持独立开关"单价"列

### 优化
- 前端刷新从 N 个独立 `fetchOne()` 改为单次 `POST /api/refresh`，响应更快
- records 积累从前端移到后端，单点写入保证不重复不遗漏
- 汇总卡片（总成本/市值/盈亏/收益率）由后端计算，前端直接渲染
- 分组标签盈亏颜色由后端 `groups_profit` 直接提供

### 修复
- `fetch_one()` JSONP 解码 bug：尾巴 `);` 未正确去除导致 `json.loads` 失败，所有基金实时数据返回 0
- 防止空数据覆盖 `funds.json`：`syncServer()` 改为从内存变量读取，`saveFunds()` 仅非空时触发
- 新增基金时立即累加今日记录，保证周/月涨幅有数据
- 添加基金不再刷新全部，仅缓存新基金数据后 render
