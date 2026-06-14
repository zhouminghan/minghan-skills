#!/usr/bin/env python3
"""
双色球科学分析脚本 - 随机策略版

读取 JSONL 格式的历史开奖数据缓存文件，
每次随机选择分析策略（期数、筛选条件、维度组合），
综合评分后输出候选红球和蓝球。
"""

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime
from itertools import combinations


def parse_jsonl_data(filepath):
    """解析 JSONL 格式的历史开奖数据文件"""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                date_str = record["date"]
                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    date = None
                records.append({
                    "issue": record["issue"],
                    "date": date,
                    "date_str": date_str,
                    "reds": record["reds"],
                    "blue": record["blue"],
                    "weekday": date.weekday() if date else None,
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return records


def choose_random_strategy(total_records):
    """随机选择本次分析策略"""
    period_choices = [30, 50, 80, 100, 150, 200, 500]
    if total_records > 500:
        period_choices.append(total_records)
    period = random.choice(period_choices)
    period = min(period, total_records)

    filter_choices = [
        {"name": "全部期数", "key": "all"},
        {"name": "仅奇数期号", "key": "odd_issue"},
        {"name": "仅偶数期号", "key": "even_issue"},
        {"name": "仅周二开奖", "key": "weekday_1"},
        {"name": "仅周四开奖", "key": "weekday_3"},
        {"name": "仅周日开奖", "key": "weekday_6"},
    ]
    data_filter = random.choice(filter_choices)

    dimension_pool = [
        "hot_cold", "missing", "odd_even", "big_small",
        "consecutive", "same_tail", "sum_value", "ac_value",
        "zone", "repeat", "prime",
    ]
    num_dims = random.randint(3, 6)
    dimensions = random.sample(dimension_pool, num_dims)

    return {
        "period": period,
        "data_filter": data_filter,
        "dimensions": dimensions,
    }


def apply_filter(records, data_filter):
    """应用数据筛选条件"""
    key = data_filter["key"]
    if key == "all":
        return records
    elif key == "odd_issue":
        return [r for r in records if int(r["issue"]) % 2 == 1]
    elif key == "even_issue":
        return [r for r in records if int(r["issue"]) % 2 == 0]
    elif key.startswith("weekday_"):
        weekday = int(key.split("_")[1])
        return [r for r in records if r["weekday"] == weekday]
    return records


# ── 分析维度函数 ──────────────────────────────────────────────────────────

def analyze_hot_cold(records):
    """冷热号统计"""
    red_counter = Counter()
    blue_counter = Counter()
    for r in records:
        for num in r["reds"]:
            red_counter[num] += 1
        blue_counter[r["blue"]] += 1

    hot_reds = [num for num, _ in red_counter.most_common(15)]
    all_red_freq = {num: red_counter.get(num, 0) for num in range(1, 34)}
    cold_reds = sorted(all_red_freq.keys(), key=lambda x: all_red_freq[x])[:10]

    hot_blues = [num for num, _ in blue_counter.most_common(8)]
    all_blue_freq = {num: blue_counter.get(num, 0) for num in range(1, 17)}
    cold_blues = sorted(all_blue_freq.keys(), key=lambda x: all_blue_freq[x])[:5]

    red_scores = {}
    for num in range(1, 34):
        if num in hot_reds:
            red_scores[num] = 2.0
        elif num in cold_reds:
            red_scores[num] = 1.5
        else:
            red_scores[num] = 1.0

    blue_scores = {}
    for num in range(1, 17):
        if num in hot_blues:
            blue_scores[num] = 2.0
        elif num in cold_blues:
            blue_scores[num] = 1.5
        else:
            blue_scores[num] = 1.0

    return {
        "red_scores": red_scores, "blue_scores": blue_scores,
        "hot_reds": hot_reds, "cold_reds": cold_reds,
        "hot_blues": hot_blues, "cold_blues": cold_blues,
    }


def analyze_missing(records):
    """遗漏值分析：统计每个号码距最后一次出现的期数间隔

    数据按时间正序排列（records[0]=最旧, records[-1]=最新）。
    遗漏值 = 该号码在数据窗口内最后一次出现的位置距窗口末尾的间隔。
    未出现的号码遗漏值 = 总期数。
    """
    total = len(records)
    red_last_pos = {}     # 记录每个号码最后一次出现的索引
    blue_last_pos = {}

    # 正序遍历，每次覆盖 → 最终保留的是最后一次（最新）出现的位置
    for i, r in enumerate(records):
        for num in r["reds"]:
            red_last_pos[num] = i
        blue_last_pos[r["blue"]] = i

    # 遗漏值 = 距窗口末尾的间隔；未出现的 = total（最大遗漏）
    red_missing = {num: (total - 1 - red_last_pos.get(num, -1)) for num in range(1, 34)}
    blue_missing = {num: (total - 1 - blue_last_pos.get(num, -1)) for num in range(1, 17)}

    top_missing_reds = sorted(red_missing.keys(), key=lambda x: red_missing[x], reverse=True)[:12]
    top_missing_blues = sorted(blue_missing.keys(), key=lambda x: blue_missing[x], reverse=True)[:6]

    return {
        "red_scores": red_missing, "blue_scores": blue_missing,
        "top_missing_reds": top_missing_reds, "top_missing_blues": top_missing_blues,
    }


def analyze_odd_even(records):
    """奇偶比分析"""
    odd_counts = [sum(1 for x in r["reds"] if x % 2 == 1) for r in records]
    avg_odd = sum(odd_counts) / len(odd_counts) if odd_counts else 3

    if avg_odd > 3.2:
        favor = "even"
        red_scores = {num: (2 if num % 2 == 0 else 1) for num in range(1, 34)}
    elif avg_odd < 2.8:
        favor = "odd"
        red_scores = {num: (2 if num % 2 == 1 else 1) for num in range(1, 34)}
    else:
        favor = "balanced"
        red_scores = {num: 1 for num in range(1, 34)}

    return {"red_scores": red_scores, "blue_scores": {num: 1 for num in range(1, 17)}, "avg_odd": round(avg_odd, 2), "favor": favor}


def analyze_big_small(records):
    """大小比分析"""
    big_counts = [sum(1 for x in r["reds"] if x >= 17) for r in records]
    avg_big = sum(big_counts) / len(big_counts) if big_counts else 3

    if avg_big > 3.2:
        favor = "small"; red_scores = {num: (2 if num < 17 else 1) for num in range(1, 34)}
    elif avg_big < 2.8:
        favor = "big"; red_scores = {num: (2 if num >= 17 else 1) for num in range(1, 34)}
    else:
        favor = "balanced"; red_scores = {num: 1 for num in range(1, 34)}

    blue_big_counts = [1 if r["blue"] >= 8 else 0 for r in records]
    avg_blue_big = sum(blue_big_counts) / len(blue_big_counts) if blue_big_counts else 0.5
    if avg_blue_big > 0.55:
        blue_scores = {num: (2 if num < 8 else 1) for num in range(1, 17)}
    elif avg_blue_big < 0.45:
        blue_scores = {num: (2 if num >= 8 else 1) for num in range(1, 17)}
    else:
        blue_scores = {num: 1 for num in range(1, 17)}

    return {"red_scores": red_scores, "blue_scores": blue_scores, "avg_big": round(avg_big, 2), "favor": favor}


def analyze_consecutive(records):
    """连号分析"""
    consecutive_pairs = Counter()
    has_consecutive = 0

    for r in records:
        sorted_reds = sorted(r["reds"])
        found = False
        for i in range(len(sorted_reds) - 1):
            if sorted_reds[i + 1] - sorted_reds[i] == 1:
                consecutive_pairs[(sorted_reds[i], sorted_reds[i + 1])] += 1
                found = True
        if found:
            has_consecutive += 1

    consecutive_rate = has_consecutive / len(records) if records else 0
    red_scores = {num: 1 for num in range(1, 34)}
    if consecutive_rate > 0.5:
        for (a, b), _ in consecutive_pairs.most_common(5):
            red_scores[a] = red_scores.get(a, 1) + 1
            red_scores[b] = red_scores.get(b, 1) + 1

    return {"red_scores": red_scores, "blue_scores": {num: 1 for num in range(1, 17)}, "consecutive_rate": round(consecutive_rate, 3), "top_pairs": [(a, b) for (a, b), _ in consecutive_pairs.most_common(5)]}


def analyze_same_tail(records):
    """同尾号分析"""
    same_tail_count = 0
    tail_pairs = Counter()

    for r in records:
        tails = [x % 10 for x in r["reds"]]
        tail_counter = Counter(tails)
        has_same = False
        for tail, count in tail_counter.items():
            if count >= 2:
                has_same = True
                nums_with_tail = [x for x in r["reds"] if x % 10 == tail]
                for pair in combinations(nums_with_tail, 2):
                    tail_pairs[pair] += 1
        if has_same:
            same_tail_count += 1

    same_tail_rate = same_tail_count / len(records) if records else 0
    red_scores = {num: 1 for num in range(1, 34)}
    if same_tail_rate > 0.4:
        for (a, b), _ in tail_pairs.most_common(5):
            red_scores[a] = red_scores.get(a, 1) + 1
            red_scores[b] = red_scores.get(b, 1) + 1

    return {"red_scores": red_scores, "blue_scores": {num: 1 for num in range(1, 17)}, "same_tail_rate": round(same_tail_rate, 3)}


def analyze_sum_value(records):
    """和值分析"""
    sums = [sum(r["reds"]) for r in records]
    avg_sum = sum(sums) / len(sums) if sums else 100
    red_scores = {num: 1 for num in range(1, 34)}
    if avg_sum > 110:
        for num in range(1, 17): red_scores[num] += 1
    elif avg_sum < 90:
        for num in range(17, 34): red_scores[num] += 1

    return {"red_scores": red_scores, "blue_scores": {num: 1 for num in range(1, 17)}, "avg_sum": round(avg_sum, 1)}


def analyze_ac_value(records):
    """AC值分析"""
    ac_values = []
    for r in records:
        diffs = set()
        sorted_reds = sorted(r["reds"])
        for i in range(len(sorted_reds)):
            for j in range(i + 1, len(sorted_reds)):
                diffs.add(sorted_reds[j] - sorted_reds[i])
        ac = len(diffs) - 5
        ac_values.append(ac)

    avg_ac = sum(ac_values) / len(ac_values) if ac_values else 7
    red_scores = {num: 1 for num in range(1, 34)}
    if avg_ac < 6:
        for num in list(range(1, 6)) + list(range(29, 34)): red_scores[num] += 1
    elif avg_ac > 8:
        for num in range(10, 24): red_scores[num] += 1

    return {"red_scores": red_scores, "blue_scores": {num: 1 for num in range(1, 17)}, "avg_ac": round(avg_ac, 2)}


def analyze_zone(records):
    """区间分布分析"""
    zone_counts = [0, 0, 0]
    for r in records:
        for num in r["reds"]:
            if num <= 11: zone_counts[0] += 1
            elif num <= 22: zone_counts[1] += 1
            else: zone_counts[2] += 1

    total = sum(zone_counts)
    zone_ratios = [c / total if total > 0 else 1 / 3 for c in zone_counts]
    red_scores = {num: 1 for num in range(1, 34)}
    for i, ratio in enumerate(zone_ratios):
        if ratio < 0.28:
            if i == 0:
                for num in range(1, 12): red_scores[num] += 2
            elif i == 1:
                for num in range(12, 23): red_scores[num] += 2
            else:
                for num in range(23, 34): red_scores[num] += 2
        elif ratio > 0.38:
            if i == 0:
                for num in range(1, 12): red_scores[num] = max(0, red_scores[num] - 1)
            elif i == 1:
                for num in range(12, 23): red_scores[num] = max(0, red_scores[num] - 1)
            else:
                for num in range(23, 34): red_scores[num] = max(0, red_scores[num] - 1)

    return {"red_scores": red_scores, "blue_scores": {num: 1 for num in range(1, 17)}, "zone_ratios": [round(r, 3) for r in zone_ratios], "zone_counts": zone_counts}


def analyze_repeat(records):
    """重号分析"""
    if len(records) < 2:
        return {"red_scores": {num: 1 for num in range(1, 34)}, "blue_scores": {num: 1 for num in range(1, 17)}, "repeat_rate": 0, "avg_repeat_count": 0}

    repeat_counts = []
    for i in range(len(records) - 1):
        current_reds = set(records[i]["reds"])
        prev_reds = set(records[i + 1]["reds"])
        repeat_counts.append(len(current_reds & prev_reds))

    has_repeat = sum(1 for c in repeat_counts if c > 0)
    repeat_rate = has_repeat / len(repeat_counts) if repeat_counts else 0
    avg_repeat = sum(repeat_counts) / len(repeat_counts) if repeat_counts else 0

    latest_reds = set(records[0]["reds"])
    latest_blue = records[0]["blue"]

    red_scores = {num: 1 for num in range(1, 34)}
    blue_scores = {num: 1 for num in range(1, 17)}

    if repeat_rate > 0.6:
        for num in latest_reds: red_scores[num] += 2
        blue_scores[latest_blue] += 2
    elif repeat_rate > 0.4:
        for num in latest_reds: red_scores[num] += 1
        blue_scores[latest_blue] += 1

    return {"red_scores": red_scores, "blue_scores": blue_scores, "repeat_rate": round(repeat_rate, 3), "avg_repeat_count": round(avg_repeat, 2), "latest_reds": sorted(latest_reds)}


def analyze_prime(records):
    """质合比分析"""
    PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31}
    prime_counts = [sum(1 for x in r["reds"] if x in PRIMES) for r in records]
    avg_prime = sum(prime_counts) / len(prime_counts) if prime_counts else 3

    red_scores = {num: 1 for num in range(1, 34)}
    if avg_prime > 3.3:
        for num in range(1, 34):
            if num not in PRIMES: red_scores[num] += 1
    elif avg_prime < 2.7:
        for num in PRIMES: red_scores[num] += 1

    BLUE_PRIMES = {2, 3, 5, 7, 11, 13}
    blue_prime_counts = [1 if r["blue"] in BLUE_PRIMES else 0 for r in records]
    avg_blue_prime = sum(blue_prime_counts) / len(blue_prime_counts) if blue_prime_counts else 0.5
    blue_scores = {num: 1 for num in range(1, 17)}
    if avg_blue_prime > 0.55:
        for num in range(1, 17):
            if num not in BLUE_PRIMES: blue_scores[num] += 1
    elif avg_blue_prime < 0.35:
        for num in BLUE_PRIMES: blue_scores[num] += 1

    return {"red_scores": red_scores, "blue_scores": blue_scores, "avg_prime": round(avg_prime, 2), "favor": "composite" if avg_prime > 3.3 else ("prime" if avg_prime < 2.7 else "balanced")}


# ── 公共工具 ───────────────────────────────────────────────────────────────

DIMENSION_MAP = {
    "hot_cold": ("冷热号统计", analyze_hot_cold),
    "missing": ("遗漏值分析", analyze_missing),
    "odd_even": ("奇偶比分析", analyze_odd_even),
    "big_small": ("大小比分析", analyze_big_small),
    "consecutive": ("连号分析", analyze_consecutive),
    "same_tail": ("同尾号分析", analyze_same_tail),
    "sum_value": ("和值分析", analyze_sum_value),
    "ac_value": ("AC值分析", analyze_ac_value),
    "zone": ("区间分布分析", analyze_zone),
    "repeat": ("重号分析", analyze_repeat),
    "prime": ("质合比分析", analyze_prime),
}


def normalize_scores(scores):
    """将分数字典归一化到 [0, 1] 区间"""
    if not scores:
        return scores
    vals = list(scores.values())
    min_v, max_v = min(vals), max(vals)
    if max_v == min_v:
        return {k: 0.5 for k in scores}
    return {k: (v - min_v) / (max_v - min_v) for k, v in scores.items()}


def main():
    parser = argparse.ArgumentParser(description="双色球科学分析脚本")
    parser.add_argument("filepath", help="JSONL 缓存文件路径")
    args = parser.parse_args()

    # 解析数据
    all_records = parse_jsonl_data(args.filepath)
    if not all_records:
        print(json.dumps({"error": "未能解析到任何开奖数据"}, ensure_ascii=False))
        sys.exit(1)

    # 随机选择策略
    strategy = choose_random_strategy(len(all_records))

    # 取最近 N 期（数据正序排列，最新在末尾）
    recent_records = all_records[-strategy["period"]:]
    filtered_records = apply_filter(recent_records, strategy["data_filter"])

    if len(filtered_records) < 20:
        filtered_records = recent_records
        strategy["data_filter"] = {"name": "全部期数（筛选后数据不足，已回退）", "key": "all"}

    # 运行各分析维度，累加评分
    red_total_scores = {num: 0 for num in range(1, 34)}
    blue_total_scores = {num: 0 for num in range(1, 17)}
    dimension_details = []

    for dim_key in strategy["dimensions"]:
        dim_name, dim_func = DIMENSION_MAP[dim_key]
        result = dim_func(filtered_records)
        dimension_details.append({
            "name": dim_name, "key": dim_key,
            "details": {k: v for k, v in result.items() if k not in ("red_scores", "blue_scores")},
        })
        normed_red = normalize_scores(result["red_scores"])
        normed_blue = normalize_scores(result["blue_scores"])
        for num, score in normed_red.items():
            red_total_scores[num] += score
        for num, score in normed_blue.items():
            blue_total_scores[num] += score

    # 随机扰动
    for num in red_total_scores:
        red_total_scores[num] += random.uniform(0, 0.15)
    for num in blue_total_scores:
        blue_total_scores[num] += random.uniform(0, 0.15)

    # 排序选出候选号码
    sorted_reds = sorted(red_total_scores.items(), key=lambda x: x[1], reverse=True)
    sorted_blues = sorted(blue_total_scores.items(), key=lambda x: x[1], reverse=True)

    num_red_candidates = random.randint(15, 18)
    candidate_reds = sorted([num for num, _ in sorted_reds[:num_red_candidates]])
    num_blue_candidates = random.randint(6, 8)
    candidate_blues = sorted([num for num, _ in sorted_blues[:num_blue_candidates]])

    dim_names = [DIMENSION_MAP[d][0] for d in strategy["dimensions"]]
    strategy_desc = (
        f"分析最近{strategy['period']}期数据，"
        f"筛选条件：{strategy['data_filter']['name']}，"
        f"实际分析{len(filtered_records)}期，"
        f"使用维度：{'、'.join(dim_names)}"
    )

    output = {
        "strategy": strategy_desc,
        "candidate_reds": candidate_reds,
        "candidate_blues": candidate_blues,
        "total_records_parsed": len(all_records),
        "records_analyzed": len(filtered_records),
        "dimension_details": dimension_details,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
