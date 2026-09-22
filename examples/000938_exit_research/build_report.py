"""将全部候选结果、配对交易和不利验证写入可审阅报告。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/exit-research-000938"
primary = json.loads((OUT / "000938-report.json").read_text())
reference = json.loads((OUT / "002396-report.json").read_text())
robust = json.loads((OUT / "robustness.json").read_text())
pct = lambda x: f"{x * 100:+.2f}%"
lines = [
    "# 卖出点研究：保留原买点，上涨后收紧保护",
    "",
    "结论：原版退出存在明显回吐。对000938，分段保护且不增加重入可以改善当前样本；对参考标的002396，整体收益基本持平且部分年份变差，尚不能称为通用精准卖点。原策略保留，新增对比候选。",
    "",
    "## 新规则的含义",
    "",
    "1. 买入条件、实际BUY信号日期保持原版。",
    "2. 初期沿用原版EMA20连续两日破位或3ATR跟随退出。",
    "3. 最高收盘价相对买入信号收盘上涨2个信号当天ATR后，激活保护；后续跟随距离从3ATR收紧为1.5ATR，跟随线只升不降，激活后不撤销。",
    "4. 提前退出后不立即重新追入；等待原策略本轮自然结束、冷却并产生下一个BUY，保留原买入节奏。",
    "",
    "例：信号收盘20元、当日ATR为1元，之后最高收盘达到22元，保护激活。若当时ATR仍为1元，跟随线至少抬至20.5元，之后随新高抬升。收盘跌破线才触发下一根开盘卖出，不保证在20.5元成交。使用的是信号价格/ATR，函数无法取得真实成交成本。",
    "",
    "源码：[strategy.py](strategy.py)。新增参数 `profit_arm_atr=2.0` 和 `profit_trailing_atr=1.5`，其他入场参数保持原样。具体数值不是优化得出的最佳值，而是少量预定候选中的研究假设。",
    "",
    "## 方法与不可忽略的边界",
    "",
    f"- 000938腾讯前复权缓存：{primary['start']} 至 {primary['end']}，{primary['bars']}根；002396为同时间范围的同业参考，不代表独立市场验证。",
    "- 所有信号只用当日及以前数据，收盘确认、下一根开盘；无当日最高价成交假设。未模拟涨跌停封单、市场冲击，前复权价格撮合不独立记分红送转。",
    "- 10万元起始，佣金0.03%且最低5元，卖出印花税0.05%，单边滑点0.1%。固定费率未模拟历史变化。",
    "- 第一层固定原买点，每笔分别从10万元开始，配对买入价、股数相同，比较退出价格和净收益。这些独立实验可能时间重叠，不能累加当成账户收益。",
    "- 第二层运行完整账户。自由重入方案虽保持入场条件，也会改变后续实际买入日；锁定原买点方案避免了这种混淆。股数会随累计资金变化。",
    "- 回吐：持有期间最高收盘到实际卖价的跌幅。开盘卖出当天的高/低/收盘不纳入持有期；仅在曾有正收盘浮盈的交易中计算回吐与滞后中位数。它是事后诊断，不表示那些收盘高点可以提前知道并成交。",
    "- 先固定3个候选并比较，发现自由重入问题后追加锁定原买点执行约束。全部历程见 [PLAN.md](PLAN.md)，未隐去失利方案。000938历史此前已用过，分段不是严格未见数据，也不能证明无过拟合。",
    "",
    "## 全部方案的完整账户表现",
    "",
    "| 退出方案 | 总收益 | 最大回撤 | 完整交易数 |",
    "| --- | ---: | ---: | ---: |",
]
for k, v in primary["full"].items():
    m = v["metrics"]
    lines.append(
        f"| {primary['names'][k]} | {pct(m['total_return'])} | {pct(m['max_drawdown'])} | {m['number_of_trades']} |"
    )
lines += [
    "",
    "## 固定原买点的退出诊断",
    "",
    "| 方案 | 21笔平均单笔净收益 | 浮盈样本数 | 回吐中位数 | 高点后卖出间隔中位数 | 改善/受损/不变 |",
    "| --- | ---: | ---: | ---: | ---: | --- |",
]
for k, z in primary["fixed_summary"].items():
    lines.append(
        f"| {primary['names'][k]} | {pct(z['mean_net_return'])} | {z['positive_peak_count']} | {z['median_giveback']:.2%} | {z['median_lag']:g}根 | {z['improved']}/{z['worsened']}/{z['equal']} |"
    )
lines += [
    "",
    "结构退出回吐看起来最低，但曾有浮盈的样本减少到15笔，完整账户收益仅6.51%；更早退出本身不是充分的改善证据。新候选与原版曾有浮盈的样本均为同一17笔。新候选按原版持有期高点统一衡量时，回吐中位数同样为8.40%。",
    "",
    "卖出后10个交易日（含卖出当日）又出现比卖价高5%以上收盘价的次数：原版9/21，锁定保护候选9/21。这个诊断没有计算再入场交易，不代表机会成本为零。",
    "",
    "## 每个原买点的配对结果",
    "",
    "| 买入日 | 原卖出日 | 新卖出日 | 原单笔净收益 | 新单笔净收益 | 改善百分点 |",
    "| --- | --- | --- | ---: | ---: | ---: |",
]
for b, a in zip(
    primary["fixed_entries"]["baseline"], primary["fixed_entries"]["locked_guard"]
):
    bt, at = b["trade"], a["trade"]
    delta = (at["net_return"] - bt["net_return"]) * 100
    lines.append(
        f"| {b['entry_date']} | {bt['exit_date']} | {at['exit_date']} | {pct(bt['net_return'])} | {pct(at['net_return'])} | {delta:+.2f} |"
    )
lines += [
    "",
    "例如2024-09-26买入，退出由10月14日提前到10月10日，单笔净收益17.10%变为27.95%；但2022-06-07买入提前退出后，净收益7.00%降为5.09%。不能只展示前者。",
    "",
    "## 时间分段：全部展示",
    "",
    "各段独立空仓、段内预热；不能把分段直接拼接当完整账户收益。分段起点也会改变原信号状态。",
    "",
    "| 标的 | 分段 | 原版收益 | 新候选收益 |",
    "| --- | --- | ---: | ---: |",
]
for r in [primary, reference]:
    for s in r["segments"]:
        lines.append(
            f"| {r['symbol']} | {s['start']}—{s['end']} | {pct(s['cases']['baseline']['metrics']['total_return'])} | {pct(s['cases']['locked_guard']['metrics']['total_return'])} |"
        )
lines += [
    "",
    "## 交叉标的与邻近参数",
    "",
    "| 标的 | 原版总收益/回撤 | 新候选总收益/回撤 |",
    "| --- | --- | --- |",
]
for r in [primary, reference]:
    b = r["full"]["baseline"]["metrics"]
    a = r["full"]["locked_guard"]["metrics"]
    lines.append(
        f"| {r['symbol']} | {pct(b['total_return'])} / {pct(b['max_drawdown'])} | {pct(a['total_return'])} / {pct(a['max_drawdown'])} |"
    )
lines += [
    "",
    "002396的固定27个买点中，新退出改善9笔、损害2笔，但平均单笔净收益变化为−0.35个百分点：少量过早退出可能抵消多次小改善。尤其2024—2025独立分段由94.00%降至52.64%，需要保留这项反证。",
    "",
    "仅检查预定保护距离附近的1.25/1.75ATR，激活条件仍为2ATR，未根据结果改默认值：",
    "",
    "| 标的 | 保护ATR倍数 | 总收益 | 最大回撤 |",
    "| --- | ---: | ---: | ---: |",
]
for symbol, z in robust.items():
    for v in z["neighbors"]:
        m = v["metrics"]
        lines.append(
            f"| {symbol} | {v['profit_trailing_atr']} | {pct(m['total_return'])} | {pct(m['max_drawdown'])} |"
        )
lines += [
    "",
    "同业标的对保护距离的结果较敏感，因此不能声称稳健性已充分证实。",
    "",
    "| 佣金与滑点同时翻倍 | 原版总收益 | 新候选总收益 |",
    "| --- | ---: | ---: |",
]
for symbol, z in robust.items():
    lines.append(
        f"| {symbol} | {pct(z['cost_stress']['baseline']['total_return'])} | {pct(z['cost_stress']['locked_guard']['total_return'])} |"
    )
lines += [
    "",
    "## 复现与文件",
    "",
    "在项目根目录、工作台已启动且已有腾讯前复权行情时：",
    "",
    "```bash",
    ".venv/bin/python examples/000938_exit_research/evaluate.py",
    ".venv/bin/python examples/000938_exit_research/evaluate.py --symbol 002396",
    ".venv/bin/python examples/000938_exit_research/robustness.py",
    ".venv/bin/python examples/000938_exit_research/build_report.py",
    ".venv/bin/python examples/000938_exit_research/build_visual.py",
    "```",
    "",
    "核心评估只读工作台，不创建实验。完整JSON和离线交互图位于 `output/exit-research-000938/`。`robustness.json` 为本次固定邻近/成本检查结果；与核心报告一同保留。交互图 `exit-comparison.html` 使用内嵌Lightweight Charts，可离线逐笔查看。",
    "",
    f"000938数据SHA256：`{primary['data_sha256']}`；002396数据SHA256：`{reference['data_sha256']}`。复现需保持行情快照、代码和费用口径一致。",
    "",
    "参考：[Bailey 等《The Probability of Backtest Overfitting》](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)、[SEC 关于历史业绩与回测的说明](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-47)。本次只借鉴减少反复试验、披露全部尝试等原则，没有估计PBO或证明未来收益。",
]
saved_path = OUT / "saved-experiment.json"
if saved_path.exists():
    saved = json.loads(saved_path.read_text())
    lines += [
        "",
        "## 工作台中的对比版本",
        "",
        f"已保存「{saved['name']}」，独立策略库版本 V{saved['revision']}，原策略保留。刷新工作台后从Python编辑器的策略版本列表载入；历史回测中也有对应结果。",
        "",
        f"策略编号：`{saved['definition_id']}`；实验编号：`{saved['run_id']}`。",
        f"实际保存源码SHA256：`{saved['code_sha256']}`。",
        "本次完整后端测试92项通过；保存后的回测与研究报告收益一致。",
    ]

(ROOT / "examples/000938_exit_research/README.md").write_text(
    "\n".join(lines) + "\n", encoding="utf-8"
)
