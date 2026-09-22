# Python 策略学习说明

你需要编写一个 `generate_signals(data, params)` 函数：根据行情判断每天是否想买入、卖出、继续持仓或继续空仓。系统负责加载数据、调用函数、撮合交易、扣费、计算收益、保存历史和画图。

```text
本地行情 + 参数 → 你的函数 → 每日信号表 → 系统回测引擎 → 交易、收益、图表、实验快照
```

这不是云端在线执行：浏览器只是编辑界面，Python 在你电脑的后端环境执行。

## 一、策略放在哪里

- 编辑器草稿自动保存在当前浏览器、当前站点的 localStorage 中（`quant.python.v1`）。`localhost:5173` 与 `127.0.0.1:5173` 属于不同站点，浏览器草稿不共享；清理网站数据可能删掉草稿。
- 点击「保存策略」后，代码、参数和名称保存在项目 `data/trading.duckdb` 的 `strategy_definitions.definition_json` 中。后续保存增加版本，可以用「载入我的策略版本」恢复。保存检查语法，不会执行策略或创建回测。
- 点击「运行回测」后，当时使用的完整源码和参数也保存进该次实验快照。以后改代码，不会改变旧实验。直接回测也会存快照，但不会自动新增一条独立策略库版本。
- 本目录的 `strategy.py` 是额外提供给你编辑的真实 Python 文件。它与数据库中的版本不会自动同步；修改文件后需要重新粘贴代码，或用 API 重新提交文件内容。
- 数据库路径可通过 `.env` 的 `DATABASE_PATH` 配置；上面是默认位置。

## 二、不一定在网页里写

可以用 VS Code / PyCharm 编辑 `strategy.py`，Python 解释器选择项目 `.venv/bin/python`。编辑完，复制**整个文件**到「Python 策略代码」框即可；只复制函数正文会漏掉 import 和默认参数。

目前网页没有文件导入按钮，也不自动扫描目录。但现有 API 可以直接接收文件源码，本说明最后给出调用方法。

## 三、函数拿到什么数据

`data` 是 pandas DataFrame。每行是一根日 K 线，按日期从早到晚排列，只有你选择的那只股票、日期区间、数据源与复权方式。不是最新行情的单行回调。

| 数据类别 | 列名 | 含义 |
| --- | --- | --- |
| 标识 | `date`, `symbol`, `adjust_type`, `data_source` | 日期、股票、复权方式、数据源 |
| 价格 | `open`, `high`, `low`, `close`, `pre_close` | 开、高、低、收、上一收盘价，价格口径跟随所选复权方式 |
| 成交 | `volume`, `amount`, `turnover` | 成交量（股）、成交额（元）、换手率（1 代表 1%） |
| 涨跌 | `change`, `pct_change` | 涨跌额、涨跌幅（1 代表 1%） |
| 均线 | `sma_5`, `sma_20` | 默认 5 / 20 日简单均线 |
| MACD | `macd_dif`, `macd_dea`, `macd_hist` | 默认 12 / 26 / 9，柱值为 2 × (DIF − DEA) |
| 其他 | `rsi`, `atr`, `boll_mid`, `boll_upper`, `boll_lower` | 默认 RSI14、ATR14、布林带20/2 |
| 其他 | `kdj_k`, `kdj_d`, `kdj_j`, `volume_ma`, `dif_slope`, `dea_slope` | KDJ9、成交量均线5、DIF/DEA单根斜率 |

例如，`data["close"]` 取得全部收盘价；`data["close"].shift(1)` 取得每一行对应的前一日收盘价。函数中 `date` 是 Python `datetime.date`。

不同数据源并非每列都有值：腾讯源没有成交额和换手率。指标刚开始预热时也会为空。不要直接删掉这些日期；预热期间返回 `NONE`。当前区间之前的历史不会自动补入做预热。

可以用 pandas / numpy 自算指标，也可导入 `app.indicators.technical` 的 `sma`、`ema`、`calculate_macd`、`calculate_rsi`、`calculate_atr`、`calculate_boll`、`calculate_kdj`、`slope`。本例重新计算指标以应用自己的周期；修改 `params` 不会自动改变输入中已经算好的标准指标。自算指标也不会自动成为图表新曲线。

系统没有自动传入财报、新闻、分钟线、盘口、其他股票、账户现金或实际成交。若将来需要这些数据，应补充数据接口，而不是假设已有相应字段。

## 四、函数输出什么

必须返回一个 DataFrame，至少含下列四列，**行数、日期和顺序与输入完全一致**。

| date | signal | position_target | reason |
| --- | --- | --- | --- |
| 2024-01-02 | NONE | 0 | 等待指标预热 |
| 2024-01-03 | BUY | 1 | 短均线上穿长均线 |
| 2024-01-04 | HOLD | 1 | 保持目标持仓 |
| 2024-01-05 | SELL | 0 | 短均线下穿长均线 |
| 2024-01-08 | NONE | 0 | 等待下次机会 |

上表只说明格式，不是本例的真实结果。`reason` 每一行都必须是非空字符串，最多 2000 字；买卖原因会用于成交标记和交易复盘。多余的输出列会被系统丢弃。

- `BUY / 1`：发出买入信号。
- `HOLD / 1`：延续目标持仓，无新买卖指令。
- `SELL / 0`：发出卖出信号。
- `NONE / 0`：继续目标空仓，无新买卖指令。

这里只支持单只股票、做多和空仓/满仓两种目标，不支持0.5仓位或做空。系统默认以当日完整日线近似尾盘决策，同日按收盘价加减滑点尝试成交，并计算整手数量、佣金和印花税；无成交量会延后，资金不足可能买不进。最后一根 K 线的信号也能成交。真实尾盘尚不知道最终收盘价和全天成交量，因此需要分钟或逐笔数据才能精确复现尾盘决策。

策略的目标状态不等于账户实际状态。本接口先计算整段信号，再执行回测，所以函数无法直接获得实际成交价、现金、股数、成交回调。不能把信号日收盘价当作真实入场价实现精确成交价止损。本例只按信号经过的K线数控制退出，未实现真实持仓止盈止损。

你只负责输出信号。系统随后输出：`signals`（信号）、`fills`（成交）、`trades`（完整买卖交易）、`equity`（每日资金）、`metrics`（收益/回撤等）、`open_position`（期末未平仓）、`rejected_orders`（未成交记录）。页面会呈现相应图表和结果。

## 五、学习这份18参数示例

完整代码见同目录 `strategy.py`，参数见 `parameters.json`。两者默认值一致，复制策略文件本身就能使用默认参数；不需要先在网页手动创建全部18个参数。

| 参数 | 默认值 | 用来学习什么 |
| --- | --- | --- |
| `fast_ma` | 5 | 短均线观察窗口 |
| `slow_ma` | 20 | 长均线观察窗口 |
| `trend_ma` | 60 | 更长趋势窗口；买入要求价格高于趋势均线 |
| `macd_fast` | 12 | MACD快速EMA |
| `macd_slow` | 26 | MACD慢速EMA |
| `macd_signal` | 9 | MACD信号线平滑 |
| `rsi_period` | 14 | RSI观察窗口 |
| `rsi_min` | 40 | 买入允许的RSI下限 |
| `rsi_max` | 75 | 买入允许的RSI上限 |
| `exit_rsi` | 35 | 持仓期间RSI低于此值退出 |
| `volume_period` | 20 | 之前若干根K线的平均成交量 |
| `volume_ratio_min` | 0.8 | 当日量至少是此前均量的几倍 |
| `atr_period` | 14 | ATR观察窗口 |
| `atr_ratio_max` | 0.10 | ATR/价格上限，0.10是10% |
| `max_signal_bars` | 30 | 买入信号后经过30根K线，发出退出信号 |
| `cooldown_bars` | 3 | 卖出信号后跳过3根K线的买入机会 |
| `use_macd_filter` | 1 | 1启用MACD买入过滤，0关闭 |
| `use_volume_filter` | 1 | 1启用成交量买入过滤，0关闭 |

买入要求：均线金叉、收盘价高于趋势均线、RSI处于范围内、ATR/价格不超过上限，并满足启用的MACD与成交量过滤。卖出时，死叉、跌破趋势均线、RSI过低或信号持有时间到期，任一条件成立即可。

先阅读代码第3段的 `buy = (...)`，再看第4段如何从条件维护 `target`。例如 `&` 表示多个条件同时满足，`|` 表示任一满足；pandas条件组合要给每个比较加括号。冷却期和过滤条件可能使某次金叉被跳过，本例不会在随后条件改善时补买，需等待下一次金叉。

参数面板目前只支持数值（整数/小数），最多50个参数。开关用0/1；不能放字符串、列表或嵌套字典。代码用 `p = {**DEFAULT_PARAMS, **params}` 合并，网页输入优先。新增一个网页参数时初值是0，需要改成有效数值。本例拒绝未使用的参数，避免拼错名称后悄悄失效；从旧示例切换时请删除不相关参数。

建议第一次按默认值校验；第二次只改 `fast_ma` 或 `slow_ma` 观察信号位置；然后把两个过滤开关设为0观察变化，再逐个打开。之后改第3段买入条件或第4段退出条件。参数用于教学，没有做收益优化，不应把条件更多理解为策略更好。

## 六、在工作台使用

1. 选择股票、日期范围、数据源和复权方式，下载或读取本地行情。至少准备足够长的区间完成60日等指标预热。
2. 切换「Python 编辑器」，把 `strategy.py` 全文粘贴到代码框，起一个策略名称。
3. 删除旧示例残留的不相关参数；可以清空面板使用代码默认值，也可按需添加本例的同名参数覆盖默认值。
4. 点击「校验策略与信号」，查看格式错误、买卖信号数和前5个信号。校验不会新增实验记录。
5. 点击「保存策略」保留版本，再点击「运行回测」生成交易、资金曲线及历史实验。

初始资金、佣金、最低佣金、印花税、滑点应在「撮合设置」中调整，不属于本例 `params`。只修改文件或只点击保存不会自动运行回测。

## 七、直接从本地文件调用现有API

下面的 Python 代码可在项目根目录用项目 `.venv/bin/python` 运行，前提是工作台服务已启动，并且已下载所选样本行情。它从磁盘读取 `.py` 和参数，**只校验、不保存**，无需使用网页代码框。

```python
import json
from pathlib import Path
import requests

folder = Path("examples/python_strategy_learning")
definition = {
    "kind": "python",
    "name": "学习：多条件均线策略",
    "description": "18参数学习示例",
    "code": (folder / "strategy.py").read_text(encoding="utf-8"),
    "parameters": json.loads((folder / "parameters.json").read_text(encoding="utf-8")),
}
query = {
    "symbol": "000938",
    "start_date": "2021-01-01",
    "end_date": "2026-01-01",
    "source": "sample",    # 模拟数据；真实来源可选 tencent 或 eastmoney
    "adjust": "qfq",
}
base = "http://127.0.0.1:8000/api"  # 如修改了API端口，这里也要修改
response = requests.post(
    base + "/strategy-editor/validate",
    json={**query, "custom_strategy": definition},
    timeout=30,
)
print(response.status_code, response.json())
response.raise_for_status()
```

如需运行并保存一次回测，将最后的请求路径换为 `/backtest`，请求体保持不变。返回结果包含新实验的 `run_id`、交易与收益，可在页面历史记录中查看；这会增加一条实验记录。

如只需保存独立策略库版本，可调用：

```python
response = requests.post(
    base + "/strategy-editor/definitions",
    json={"definition": definition},
    timeout=30,
)
response.raise_for_status()
print(response.json()["definition_id"])
```

保存新版本时传 `parent_id`（之前返回的 definition_id），即 `{"definition": definition, "parent_id": "之前的编号"}`；不传则另建一个策略。编辑器策略下拉列表在页面载入时读取，外部保存后刷新页面可见。

## 八、写策略时记住三点

- 每个日期只能使用当日收盘前已知的数据。`shift(1)`、向后看的rolling通常符合此要求；`shift(-1)`、`rolling(center=True)`、全区间最高最低价用来决定历史信号会引入未来数据。
- 系统抽查两段历史前缀，因此函数可能执行3次。保持确定性，不在函数里下载随机变化的数据、写外部文件或更新全局计数器。15秒是整个子进程（含抽查）的时间预算；抽查通过不代表严格证明没有未来信息。
- 使用 `reason` 说明触发因素，先核对交易原因、信号日和成交日，再看汇总收益。

## 本例验证

2026-09-21：在独立临时数据库和模拟数据中，通过实际 `/strategy-editor/validate`、`/backtest` 调用及历史源码恢复检查；额外检查短预热区间、7个截断前缀、3组参数变化和6种非法参数。不向用户研究数据库新增策略或实验。
