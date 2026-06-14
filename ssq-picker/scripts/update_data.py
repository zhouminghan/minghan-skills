#!/usr/bin/env python3
"""
双色球开奖数据更新脚本

从网络获取最新开奖数据，写入/追加到本地 JSONL 缓存文件。
支持两种模式：
  1. --init：首次初始化，全量拉取所有历史数据
  2. 默认（增量）：拉取最近 N 期，与本地缓存比对后仅追加新数据

数据源（按优先级自动切换）：
  1. 500彩票网 (datachart.500.com) — 首选，HTML表格解析，无需key
  2. 福彩官方API (cwl.gov.cn) — 需先访问首页拿cookie，否则403
"""

import argparse
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:
    print(json.dumps({
        "error": "缺少 requests 库，请运行: pip3 install requests",
    }, ensure_ascii=False))
    sys.exit(1)


COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# ── 500彩票网 HTML 解析正则 ──────────────────────────────────────────────
_RE_ROW = re.compile(r'<tr class="t_tr1">.*?</tr>', re.DOTALL)
_RE_RED = re.compile(r'<td class="t_cfont2">(\d+)</td>')
_RE_BLUE = re.compile(r'<td class="t_cfont4">(\d+)</td>')
_RE_ISSUE = re.compile(r'<td>(\d{5})</td>')
_RE_DATE = re.compile(r'<td>(\d{4}-\d{2}-\d{2})</td>')


def fetch_from_500(count=50):
    """从500彩票网获取数据（解析 HTML 表格）

    返回 list[dict]，每个 dict: {issue, date, reds: [int], blue: int}
    """
    url = "https://datachart.500.com/ssq/history/newinc/history.php"
    params = {"start": "03001", "end": "99999"}
    if count > 0:
        params["limit"] = str(count)

    try:
        resp = requests.get(url, params=params, headers=COMMON_HEADERS, timeout=30)
        resp.raise_for_status()
        html = resp.text
        rows = _RE_ROW.findall(html)
        if not rows:
            return None, "500彩票网未匹配到数据行，页面格式可能已变化"

        draws = []
        for row in rows:
            issue_m = _RE_ISSUE.search(row)
            reds = _RE_RED.findall(row)
            blue_m = _RE_BLUE.search(row)
            date_m = _RE_DATE.search(row)
            if not (issue_m and len(reds) == 6 and blue_m and date_m):
                continue
            short_issue = issue_m.group(1)
            date = date_m.group(1)
            year = date[:4]
            issue = year[:2] + short_issue
            draws.append({
                "issue": issue,
                "date": date,
                "reds": sorted(int(r) for r in reds),
                "blue": int(blue_m.group(1)),
            })

        if not draws:
            return None, "500彩票网数据行解析失败"

        draws.sort(key=lambda x: x["issue"])
        print(json.dumps({"status": f"500彩票网获取成功，共 {len(draws)} 期"}, ensure_ascii=False))
        return draws, None

    except Exception as e:
        return None, f"500彩票网获取失败: {e}"


def fetch_from_cwl(count=50):
    """从福彩官方API获取数据（需先访问首页拿cookie）"""
    url = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
    params = {"name": "ssq", "issueCount": count}
    headers = {
        **COMMON_HEADERS,
        "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        sess = requests.Session()
        sess.headers.update(COMMON_HEADERS)
        try:
            sess.get("https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/", timeout=15)
        except Exception:
            pass
        resp = sess.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        draws = []
        for item in data.get("result", []):
            red = sorted(int(x) for x in item["red"].split(","))
            blue = int(item["blue"])
            draws.append({
                "issue": item["code"],
                "date": item["date"][:10],
                "reds": red,
                "blue": blue,
            })
        if draws:
            print(json.dumps({"status": f"福彩官方API获取成功，共 {len(draws)} 期"}, ensure_ascii=False))
            return draws, None
        return None, "福彩官方API返回数据为空"
    except Exception as e:
        return None, f"福彩官方API失败: {e}"


def fetch_latest_data(count=50, max_retries=3):
    """依次尝试多个数据源，返回获取到的开奖数据

    优先级: 500彩票网 → 福彩官方
    """
    sources = [
        ("500彩票网", fetch_from_500),
        ("福彩官方", fetch_from_cwl),
    ]
    for name, fetcher in sources:
        print(json.dumps({"status": f"尝试数据源: {name}"}, ensure_ascii=False))
        for attempt in range(max_retries):
            draws, error = fetcher(count)
            if draws:
                return draws, None
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
        print(json.dumps({"warning": f"{name} 获取失败: {error}"}, ensure_ascii=False))
        time.sleep(1)

    return None, "所有数据源均获取失败，请检查网络连接或稍后重试"


def load_local_issues(filepath):
    """读取 JSONL 缓存文件，返回已有期号集合和总记录数"""
    issues = set()
    total = 0
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    issues.add(record["issue"])
                    total += 1
                except (json.JSONDecodeError, KeyError):
                    continue
    return issues, total


def append_new_records(filepath, new_records):
    """将新记录追加到 JSONL 文件末尾（按 issue 排序）"""
    new_records.sort(key=lambda x: x["issue"])

    # 确保目录存在
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    with open(filepath, "a", encoding="utf-8") as f:
        for r in new_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_full_cache(filepath, all_records):
    """首次初始化：全量写入 JSONL 文件（覆盖模式）"""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="双色球开奖数据更新脚本")
    parser.add_argument("filepath", nargs="?", default=None, help="JSONL 缓存文件路径")
    parser.add_argument("--init", action="store_true", help="首次初始化模式：全量拉取历史数据")
    parser.add_argument("--count", type=int, default=50, help="增量模式下获取最近N期（默认50），--init 时拉取全量")
    args = parser.parse_args()

    is_init = args.init
    filepath = args.filepath

    # --init 模式不要求传入 filepath，默认用 data/draws.jsonl
    if is_init and not filepath:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(project_dir, "data", "draws.jsonl")

    print(json.dumps({"status": "开始获取开奖数据..."}, ensure_ascii=False))

    # 拉取数量：init 模式给一个大数让 500 网返回全部；增量模式默认最近 50 期
    fetch_count = 0 if is_init else args.count  # 500 网不传 limit 或 limit=0 会返回较多数据

    remote_records, error = fetch_latest_data(fetch_count)
    if error:
        print(json.dumps({"error": error}, ensure_ascii=False))
        sys.exit(1)

    if not remote_records:
        print(json.dumps({"error": "未获取到任何数据"}, ensure_ascii=False))
        sys.exit(1)

    if is_init:
        # 首次初始化：直接全量写入
        write_full_cache(filepath, remote_records)
        latest = remote_records[-1]
        result = {
            "status": "初始化完成",
            "total": len(remote_records),
            "latest_issue": latest["issue"],
            "latest_date": latest["date"],
            "latest_reds": latest["reds"],
            "latest_blue": latest["blue"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 增量更新模式
    local_issues, total = load_local_issues(filepath)

    new_records = [r for r in remote_records if r["issue"] not in local_issues]

    if not new_records:
        latest = remote_records[-1]
        result = {
            "status": "已是最新",
            "added_count": 0,
            "total": total,
            "latest_issue": latest["issue"],
            "latest_date": latest["date"],
            "latest_reds": latest["reds"],
            "latest_blue": latest["blue"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    append_new_records(filepath, new_records)

    latest = new_records[-1]
    result = {
        "status": "更新成功",
        "added_count": len(new_records),
        "total": total + len(new_records),
        "latest_issue": latest["issue"],
        "latest_date": latest["date"],
        "latest_reds": latest["reds"],
        "latest_blue": latest["blue"],
        "new_issues": [r["issue"] for r in new_records],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
