"""
fund-server (Flask)
├── 持久层: funds.json 读写
├── 抓取层: 并发抓取 1234567 实时估值
├── 计算层: compute_funds() 单函数输出所有衍生数据
└── 路由: /api/config /api/save /api/compute /api/refresh
"""
import json, os, threading, re, sys
from datetime import date, timedelta, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, render_template, request

if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

app = Flask(__name__)
DATA_FILE = os.path.join(os.path.dirname(__file__), 'funds.json')
FILE_LOCK = threading.Lock()
FETCH_TIMEOUT = 15


# ── 持久层 ──

def read_config():
    if not os.path.exists(DATA_FILE):
        example = os.path.join(os.path.dirname(__file__), 'funds.example.json')
        if os.path.exists(example):
            try:
                with open(example, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {"groups": [], "funds": []}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"groups": [], "funds": []}


def write_config(data):
    with FILE_LOCK:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ── 数据抓取 ──

def fetch_one(code):
    try:
        r = requests.get(
            f'https://fundgz.1234567.com.cn/js/{code}.js',
            timeout=FETCH_TIMEOUT
        )
        r.encoding = 'utf-8'
        text = r.text.strip()
        m = re.match(r'^jsonpgz\((.*)\);?\s*$', text)
        if m:
            text = m.group(1)
        data = json.loads(text)
        return {
            'fundcode': data['fundcode'],
            'name': data['name'],
            'dwjz': float(data['dwjz']),
            'gsz': float(data['gsz']),
            'gztime': data['gztime'],
        }
    except Exception:
        return None


def fetch_official_nav(code):
    try:
        r = requests.get(
            f'https://api.fund.eastmoney.com/f10/lsjz?callback=jquery&fundCode={code}&pageIndex=1&pageSize=1',
            headers={'Referer': 'https://fund.eastmoney.com/'},
            timeout=FETCH_TIMEOUT,
        )
        text = r.text.strip()
        m = re.match(r'^jquery\((.*)\);?\s*$', text, re.IGNORECASE)
        if m:
            text = m.group(1)
        data = json.loads(text)
        if data.get('Data') and data['Data'].get('LSJZList'):
            nav = data['Data']['LSJZList'][0]
            dwjz = float(nav['DWJZ'])
            if dwjz > 0 and nav.get('FSRQ') == date.today().isoformat():
                return dwjz
    except Exception:
        pass
    return None


# ── 计算层 ──

def calc_periods(records):
    if not records:
        return {}
    sorted_r = sorted(records, key=lambda x: x['d'])
    latest = datetime.strptime(sorted_r[-1]['d'], '%Y-%m-%d').date()

    def sum_days(days):
        cut = latest - timedelta(days=days)
        filtered = [
            r for r in sorted_r
            if datetime.strptime(r['d'], '%Y-%m-%d').date() >= cut
        ]
        if not filtered:
            return None
        return round(sum(r['v'] for r in filtered), 2)

    return {
        'w1': sum_days(7),
        'w2': sum_days(14),
        'm1': sum_days(30),
        'm3': sum_days(90),
        'y1': sum_days(365),
        'sinceAdd': round(sum(r['v'] for r in sorted_r), 2),
    }


def compute_funds(funds, live, groups, cur_group='all'):
    """
    全量衍生计算，供 /api/compute 和 /api/refresh 共用。
    返回: {rows, summary, groupsProfit, groupBreakdown}
    """
    # ── 构建 rows（过滤 + 同代码合并） ──
    if cur_group == 'all':
        merged = {}
        for f in funds:
            if not f.get('shares') or f.get('shares', 0) <= 0:
                continue
            code = f['code']
            if code in merged:
                m = merged[code]
                old_total = (m.get('cost', 0) or 0) * (m.get('shares', 0) or 0)
                add_total = (f.get('cost', 0) or 0) * (f.get('shares', 0) or 0)
                m['shares'] = (m.get('shares', 0) or 0) + (f.get('shares', 0) or 0)
                m['cost'] = round((old_total + add_total) / m['shares'], 6) if m['shares'] > 0 else 0
                m['todayBuy'] = (m.get('todayBuy', 0) or 0) + (f.get('todayBuy', 0) or 0)
                if f.get('addTime') and f['addTime'] < (m.get('addTime') or ''):
                    m['addTime'] = f['addTime']
            else:
                merged[code] = dict(f)
        fund_rows = list(merged.values())
    else:
        fund_rows = [dict(f) for f in funds if f.get('groupId') == cur_group]

    # ── 逐行计算 ──
    rows = []
    total_cost = total_value = total_profit = total_today = 0.0

    for f in fund_rows:
        code = f['code']
        d = live.get(code) if isinstance(live, dict) else None
        shares = f.get('shares', 0) or 0
        has_pos = shares > 0
        row = dict(f)

        if d and d.get('gsz') is not None:
            gsz = float(d['gsz'])
            dwjz = float(d.get('dwjz', 0) or 0)
            row['gsz'] = gsz
            row['dwjz'] = dwjz
            row['gztime'] = d.get('gztime', '')
            row['pct'] = round((gsz - dwjz) / dwjz * 100, 4) if dwjz > 0 else 0.0
            row['periods'] = calc_periods(f.get('records', []))
            row['hasData'] = True
        else:
            gsz = dwjz = 0.0
            row['gsz'] = 0.0
            row['dwjz'] = 0.0
            row['gztime'] = None
            row['pct'] = 0.0
            row['periods'] = {}
            row['hasData'] = False

        row['hasPos'] = has_pos

        if row['hasData'] and has_pos:
            cost = f.get('cost', 0) or 0
            total_paid = round(shares * cost, 2)
            cur_val = round(shares * gsz, 2)
            profit = round(cur_val - total_paid, 2)
            today_profit = round(shares * (gsz - dwjz), 2) if dwjz > 0 else 0.0
            row['totalPaid'] = total_paid
            row['curVal'] = cur_val
            row['profit'] = profit
            row['todayProfit'] = today_profit
            total_cost += total_paid
            total_value += cur_val
            total_profit += profit
            total_today += today_profit
        else:
            row['totalPaid'] = 0.0
            row['curVal'] = 0.0
            row['profit'] = 0.0
            row['todayProfit'] = 0.0

        rows.append(row)

    # ── 分组盈亏（供 tab 标签使用） ──
    groups_profit = {}
    for f in funds:
        gid = f.get('groupId')
        if not gid:
            continue
        shares = f.get('shares', 0) or 0
        if shares <= 0:
            continue
        if gid not in groups_profit:
            groups_profit[gid] = {'profit': 0.0, 'todayProfit': 0.0, 'cost': 0.0, 'hasLive': False}
        gp = groups_profit[gid]
        cost = f.get('cost', 0) or 0
        total_paid = round(shares * cost, 2)
        gp['cost'] += total_paid
        d = live.get(f['code']) if isinstance(live, dict) else None
        if not d or d.get('gsz') is None:
            continue
        gp['hasLive'] = True
        gsz = float(d['gsz'])
        dwjz = float(d.get('dwjz', 0) or 0)
        gp['profit'] += round(shares * gsz - total_paid, 2)
        if dwjz > 0:
            gp['todayProfit'] += round(shares * (gsz - dwjz), 2)

    # ── 分组明细（供「全部」tab 展示） ──
    group_breakdown = []
    for g in groups:
        if g.get('watchlist'):
            continue
        gid = g['id']
        gp = groups_profit.get(gid)
        if not gp or gp['cost'] <= 0:
            continue
        group_breakdown.append({
            'gid': gid,
            'name': g['name'],
            'profit': round(gp['profit'], 2),
            'todayProfit': round(gp['todayProfit'], 2),
            'cost': round(gp['cost'], 2),
            'hasLive': gp['hasLive'],
        })

    groups_profit_rounded = {
        k: {
            'profit': round(v['profit'], 2),
            'todayProfit': round(v['todayProfit'], 2),
            'cost': round(v['cost'], 2),
            'hasLive': v['hasLive'],
        }
        for k, v in groups_profit.items()
    }

    return {
        'rows': rows,
        'summary': {
            'totalCost': round(total_cost, 2),
            'totalValue': round(total_value, 2),
            'totalProfit': round(total_profit, 2),
            'totalToday': round(total_today, 2),
            'totalPct': round(total_profit / total_cost * 100, 2) if total_cost > 0 else 0.0,
        },
        'groupsProfit': groups_profit_rounded,
        'groupBreakdown': group_breakdown,
    }


# ── 路由 ──

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config')
def api_config():
    return read_config()


@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.get_json(force=True)
    current = read_config()
    current['groups'] = data.get('groups', current.get('groups', []))
    current['funds'] = data.get('funds', current.get('funds', []))
    write_config(current)
    return {'ok': True}

@app.route('/api/fetch-one', methods=['POST'])
def api_fetch_one():
    """由后端代理抓取单只基金数据，盘后自动用官方净值修正 gsz"""
    data = request.get_json(force=True)
    code = data.get('code', '')
    if not code or len(code) != 6:
        return {'ok': False}, 400
    d = fetch_one(code)
    if not d:
        return {'ok': False}, 404
    return {'ok': True, 'data': d}


@app.route('/api/compute', methods=['POST'])
def api_compute():
    """
    纯计算接口，不抓取实时数据。
    前端在切换分组、买入、加仓等操作后调用，获得最新衍生数据。
    """
    data = request.get_json(force=True)
    funds = data.get('funds', [])
    groups = data.get('groups', [])
    cur_group = data.get('curGroup', 'all')
    fetched = data.get('fetched', {})

    result = compute_funds(funds, fetched, groups, cur_group)
    result['funds'] = funds
    result['fetched'] = fetched
    result['groups'] = groups
    return result


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """抓取实时数据 → 修正 todayBuy → 积累 records → 全量计算"""
    config = read_config()
    funds = config.get('funds', [])
    groups = config.get('groups', [])
    if not funds:
        return {
            'funds': [], 'fetched': {}, 'groups': groups,
            'rows': [], 'summary': {
                'totalCost': 0, 'totalValue': 0,
                'totalProfit': 0, 'totalToday': 0, 'totalPct': 0,
            },
            'groupsProfit': {}, 'groupBreakdown': [],
        }

    today = date.today().isoformat()

    # 并发抓取
    live = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        future_map = {pool.submit(fetch_one, f['code']): f['code'] for f in funds}
        for fut in as_completed(future_map):
            code = future_map[fut]
            try:
                live[code] = fut.result()
            except Exception:
                live[code] = None

    # 尝试用官方净值替代 gsz（仅当日期匹配 today 才生效）
    codes_to_fix = [f['code'] for f in funds if live.get(f['code'])]
    with ThreadPoolExecutor(max_workers=10) as pool:
        nav_future = {pool.submit(fetch_official_nav, code): code for code in set(codes_to_fix)}
        for fut in as_completed(nav_future):
            code = nav_future[fut]
            try:
                nav = fut.result()
                if nav and nav > 0 and live.get(code):
                    live[code]['gsz'] = nav
            except Exception:
                pass

    # 修正 todayBuy: 用最新 gsz 重算份额
    changed = False
    for f in funds:
        tb = f.get('todayBuy', 0)
        if tb > 0 and live.get(f['code']):
            price = live[f['code']]['gsz']
            if price > 0:
                f['cost'] = price
                f['shares'] = round(tb / price, 6)
                f['todayBuy'] = 0
                changed = True

    # 积累 records（单点写入，保证不重复）
    for f in funds:
        d = live.get(f['code'])
        if not d:
            continue
        if 'records' not in f:
            f['records'] = []
        if not any(r['d'] == today for r in f['records']):
            gsz, dwjz = d.get('gsz'), d.get('dwjz')
            if gsz and dwjz and dwjz > 0:
                f['records'].append({
                    'd': today,
                    'v': round((gsz - dwjz) / dwjz * 100, 4),
                })

    write_config(config)

    # 构造 fetched 字典
    fetched = {}
    for code, d in live.items():
        if d:
            fetched[code] = {
                'gsz': d['gsz'],
                'dwjz': d['dwjz'],
                'name': d['name'],
                'gztime': d['gztime'],
            }

    result = compute_funds(funds, live, groups, 'all')
    result['funds'] = funds
    result['fetched'] = fetched
    result['groups'] = groups
    return result


if __name__ == '__main__':
    print('→ http://localhost:5000')
    print('→ http://<your-lan-ip>:5000  (手机浏览器访问)')
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
