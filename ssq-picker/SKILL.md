---
name: ssq-picker
description: "双色球智能选号工具。输入：用户说选号/买彩票/推荐号码/更新数据/对奖等。输出：一注格式化号码（6红+1蓝）含科学分析和玄学解读。排除：其他彩种、统计分析研究。当用户提到【双色球/ssq/选号/下期/选一注/买彩票/推荐号码/看看下期/帮我选/开奖/中奖/更新数据/对奖】等任意关键词时，必须【在第一轮回复前】优先调用 use_skill 加载本技能，严禁凭记忆直接执行脚本或输出结果。每轮对话必须重新 use_skill。"
---

# 双色球选号 Skill

> 🔧 操作流程（必读）→ 📖 参考资料（按需查阅）

**规则**：红球 01~33 选 6（不重复，顺序无关），蓝球 01~16 选 1，一注 = 6红 + 1蓝。
**数据**：`{SKILL_DIR}/data/draws.jsonl`，JSONL 格式，首次自动创建并全量拉取，后续增量追加。

---

## Workflow

1. Check data file exists; initialize if missing (`scripts/update_data.py --init`)
2. Update draw data incrementally (`scripts/update_data.py`, skip on network failure)
3. Randomly select mode: Science→Divination or Divination→Science
4. Run analysis scripts to get candidate red/blue balls
5. Apply a randomly chosen divination system to finalize 6 red + 1 blue
6. Determine target period (last period + 1, or user-specified)
7. Output formatted result (see `references/output-format.md`)

## 🔧 操作流程

### Step -1：数据初始化（首次使用）

```bash
ls "{SKILL_DIR}/data/draws.jsonl" 2>/dev/null && echo "EXISTS" || echo "MISSING"
```

若 **MISSING**：

```bash
mkdir -p "{SKILL_DIR}/data"
python3 {SKILL_DIR}/scripts/update_data.py --init
```

### Step 0：数据新鲜度检查

```bash
python3 {SKILL_DIR}/scripts/update_data.py "{SKILL_DIR}/data/draws.jsonl"
```

已是最新则秒级返回；有新数据则追加；网络不通则跳过用本地缓存。

### 错误处理（fallback）

1. 数据更新失败 → 告知"数据可能非最新"，继续用本地数据
2. 分析脚本失败 → 纯随机选号，标注 `⚠️ 随机模式`
3. 一次失败即 fallback，不重试

### Step 1：随机选模式

每次**随机选一种**，不要总是同一种：

**模式一：科学→玄学**
1. `python3 {SKILL_DIR}/scripts/analyze.py "{SKILL_DIR}/data/draws.jsonl"` → 输出候选红蓝球 JSON
2. 随机选一种玄学体系（见 `references/divination-systems.md`），从候选中定夺 6红+1蓝

**模式二：玄学→科学**
1. 随机选一种玄学体系，AI 推演候选池（红球 12~20 个，蓝球 4~10 个）
2. `python3 {SKILL_DIR}/scripts/scientific_pick.py "{SKILL_DIR}/data/draws.jsonl" --reds "候选红球" --blues "候选蓝球"` → 多维评分精选 6+1

> 选号规则：红球必须从候选红球中选 6 个并从小到大排列；蓝球从候选蓝球中选 1 个；必须根据当前日期独立推演，严禁套用示例数字；解读简短有趣（2-3句）。

### Step 2：确定预测期数

- 默认：JSONL 最后一行期号 +1
- 跨年：当前日期已入新年但最新期号属上一年 → `新年份001`
- 用户指定则用指定值

### Step 3：按标准格式输出

详见 `{SKILL_DIR}/references/output-format.md`。

---

### 独立功能：仅更新数据

用户只想更新数据/开奖/对奖时，不执行选号流程：

```bash
python3 {SKILL_DIR}/scripts/update_data.py "{SKILL_DIR}/data/draws.jsonl"
```

报告：新增期数、最新一期号码、或"已是最新"。

---

## 📖 参考资料

| 文件 | 内容 |
|------|------|
| `references/scientific-systems.md` | 科学分析体系（11种维度：冷热号、遗漏值、奇偶比等） |
| `references/divination-systems.md` | 玄学体系列表（12种：东方6/西方5/通用1） |
| `references/output-format.md` | 标准输出格式模板 |
