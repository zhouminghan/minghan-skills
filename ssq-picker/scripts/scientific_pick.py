#!/usr/bin/env python3
"""
双色球科学精选脚本 - 从候选池中选 6+1

用于「玄学→科学」模式的第二阶段：
接收玄学阶段产出的候选红球池和候选蓝球池，
结合历史数据进行多维科学分析评分，从候选池中精选最终 6 红 + 1 蓝。
"""

import argparse
import json
import os
import random
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

from analyze import (
    DIMENSION_MAP,
    apply_filter,
    choose_random_strategy,
    normalize_scores,
    parse_jsonl_data,
)


def main():
    parser = argparse.ArgumentParser(description="双色球科学精选脚本 - 从候选池选 6+1")
    parser.add_argument("filepath", help="JSONL 缓存文件路径")
    parser.add_argument("--reds", required=True, help="候选红球列表，逗号分隔，如: 1,3,5,8,12,15,18,21,25,28,30")
    parser.add_argument("--blues", required=True, help="候选蓝球列表，逗号分隔，如: 2,5,8,11,14")
    args = parser.parse_args()

    # 解析候选号码
    try:
        candidate_reds = sorted(set(int(x.strip()) for x in args.reds.split(",")))
        candidate_blues = sorted(set(int(x.strip()) for x in args.blues.split(",")))
    except ValueError:
        print(json.dumps({"error": "候选号码格式错误，请使用逗号分隔的数字"}, ensure_ascii=False))
        sys.exit(1)

    # 验证范围
    if not all(1 <= x <= 33 for x in candidate_reds):
        print(json.dumps({"error": "红球候选号码必须在 1-33 范围内"}, ensure_ascii=False))
        sys.exit(1)
    if not all(1 <= x <= 16 for x in candidate_blues):
        print(json.dumps({"error": "蓝球候选号码必须在 1-16 范围内"}, ensure_ascii=False))
        sys.exit(1)
    if len(candidate_reds) < 6:
        print(json.dumps({"error": f"红球候选至少需要 6 个，当前只有 {len(candidate_reds)} 个"}, ensure_ascii=False))
        sys.exit(1)
    if len(candidate_blues) < 1:
        print(json.dumps({"error": "蓝球候选至少需要 1 个"}, ensure_ascii=False))
        sys.exit(1)

    # 解析历史数据
    all_records = parse_jsonl_data(args.filepath)
    if not all_records:
        print(json.dumps({"error": "未能解析到任何开奖数据"}, ensure_ascii=False))
        sys.exit(1)

    # 随机策略
    strategy = choose_random_strategy(len(all_records))
    # 取最近 N 期（数据正序排列，最新在末尾）
    recent_records = all_records[-strategy["period"]:]
    filtered_records = apply_filter(recent_records, strategy["data_filter"])
    if len(filtered_records) < 20:
        filtered_records = recent_records
        strategy["data_filter"] = {"name": "全部期数（筛选后数据不足，已回退）", "key": "all"}

    # 对候选号码评分
    red_scores = {num: 0.0 for num in candidate_reds}
    blue_scores = {num: 0.0 for num in candidate_blues}
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
        for num in candidate_reds:
            red_scores[num] += normed_red.get(num, 0)
        for num in candidate_blues:
            blue_scores[num] += normed_blue.get(num, 0)

    # 随机扰动
    for num in red_scores:
        red_scores[num] += random.uniform(0, 0.15)
    for num in blue_scores:
        blue_scores[num] += random.uniform(0, 0.15)

    # 排序选出最终号码
    sorted_reds = sorted(red_scores.items(), key=lambda x: x[1], reverse=True)
    sorted_blues = sorted(blue_scores.items(), key=lambda x: x[1], reverse=True)

    final_reds = sorted([num for num, _ in sorted_reds[:6]])
    final_blue = sorted_blues[0][0]

    dim_names = [DIMENSION_MAP[d][0] for d in strategy["dimensions"]]
    strategy_desc = (
        f"分析最近{strategy['period']}期数据，"
        f"筛选条件：{strategy['data_filter']['name']}，"
        f"实际分析{len(filtered_records)}期，"
        f"使用维度：{'、'.join(dim_names)}"
    )

    output = {
        "strategy": strategy_desc,
        "final_reds": final_reds,
        "final_blue": final_blue,
        "candidate_reds_input": candidate_reds,
        "candidate_blues_input": candidate_blues,
        "red_scores": {str(k): round(v, 2) for k, v in sorted_reds},
        "blue_scores": {str(k): round(v, 2) for k, v in sorted_blues},
        "records_analyzed": len(filtered_records),
        "dimension_details": dimension_details,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
