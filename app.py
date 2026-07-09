"""
fund-server (Flask)
├── 功能：基金实时看板服务端，提供配置读写 + 实时数据抓取 + 衍生计算
├── 调用链：
│   ├── GET  / → 返回 index.html
│   ├── GET  /api/config → 读取 funds.json 返回 groups + funds
│   ├── POST /api/save → 接收 JSON 写入 funds.json（带锁）
│   └── POST /api/refresh → 抓取全量数据 → 积累 records → 返回计算后数据
├── 关键设计：
│   ├── /api/refresh 为唯一 records 写入点，保证单点不重复
│   ├── compute_funds() 输出全量衍生字段，前端只做渲染
│   └── ThreadPoolExecutor 并发抓取，FILE_LOCK 保护写入
├── 运行：python app.py
└── 依赖：flask, requests
"""
import json, os, threading, re
from datetime import date, timedelta, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, render_template, request

app = Flask(__name__)
DATA_FILE = os.path.join(os.path.dirname(__file__), 'funds.json')
FILE_LOCK = threading.Lock()
FETCH_TIMEOUT = 15


# ── 持久层 ──────────────────────────────────────────────

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


# ── 数据抓取 ────────────────────────────────────────────

def fetch_one(code):
    """从 1234567 抓取单只基金实时数据，返回 dict 或 None"""
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


# ── 计算层 ──────────────────────────────────────────────

def calc_periods(records):
    """从 records 数组计算各周期涨幅"""
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


def compute_funds(funds, live):
    """为每只基金计算衍生字段，同时返回汇总 + 分组盈亏"""
    rows = []
    total_cost = total_value = total_profit = total_today = 0.0

    for f in funds:
        code = f['code']
        d = live.get(code)
        row = dict(f)
        shares = f.get('shares', 0)
        has_pos = shares > 0

        if d:
            row['gsz'] = d['gsz']
            row['dwjz'] = d['dwjz']
            row['gztime'] = d['gztime']
            dwjz = d['dwjz']
            row['pct'] = round(
                (d['gsz'] - dwjz) / dwjz * 100, 4
            ) if dwjz > 0 else 0.0
            row['periods'] = calc_periods(f.get('records', []))
            row['has_data'] = True
        else:
            row['gsz'] = 0.0
            row['dwjz'] = 0.0
            row['gztime'] = None
            row['pct'] = 0.0
            row['periods'] = {}
            row['has_data'] = False

        row['has_pos'] = has_pos

        if row['has_data'] and has_pos:
            cost = f['cost']
            total_paid = round(shares * cost, 2)
            cur_val = round(shares * row['gsz'], 2)
            profit = round(cur_val - total_paid, 2)
            today_profit = round(
                shares * (row['gsz'] - row['dwjz']), 2
            ) if row['dwjz'] > 0 else 0.0

            row['total_paid'] = total_paid
            row['cur_val'] = cur_val
            row['profit'] = profit
            row['today_profit'] = today_profit

            total_cost += total_paid
            total_value += cur_val
            total_profit += profit
            total_today += today_profit
        else:
            row['total_paid'] = 0.0
            row['cur_val'] = 0.0
            row['profit'] = 0.0
            row['today_profit'] = 0.0

        rows.append(row)

    # 分组盈亏
    groups_profit = {}
    for r in rows:
        gid = r.get('groupId')
        if gid:
            groups_profit[gid] = groups_profit.get(gid, 0.0) + r.get('profit', 0.0)

    return {
        'funds': rows,
        'summary': {
            'total_cost': round(total_cost, 2),
            'total_value': round(total_value, 2),
            'total_profit': round(total_profit, 2),
            'total_today': round(total_today, 2),
            'total_pct': round(
                total_profit / total_cost * 100, 2
            ) if total_cost > 0 else 0.0,
        },
        'groups_profit': {k: round(v, 2) for k, v in groups_profit.items()},
    }


# ── 路由 ────────────────────────────────────────────────

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


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """抓取所有基金 → 积累 records → 保存 → 返回全量计算数据"""
    config = read_config()
    funds = config.get('funds', [])
    if not funds:
        return {
            'funds': [],
            'summary': {
                'total_cost': 0, 'total_value': 0,
                'total_profit': 0, 'total_today': 0, 'total_pct': 0,
            },
            'groups_profit': {},
            'groups': config.get('groups', []),
        }

    today = date.today().isoformat()

    # 并发抓取
    live = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        future_map = {
            pool.submit(fetch_one, f['code']): f['code']
            for f in funds
        }
        for fut in as_completed(future_map):
            code = future_map[fut]
            try:
                live[code] = fut.result()
            except Exception:
                live[code] = None

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

    # 保存后再计算（这样计算时能读到刚写入的 records）
    write_config(config)

    result = compute_funds(funds, live)
    result['groups'] = config.get('groups', [])
    return result


if __name__ == '__main__':
    print('→ http://localhost:5000')
    print('→ http://<your-lan-ip>:5000  (手机浏览器访问)')
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
