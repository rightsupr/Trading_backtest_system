# 研序 · Local Stock Research V0.1

本地 A 股日线策略研究、回测与逐笔复盘工具。Python 3.12+ / FastAPI / DuckDB / Pandas / NumPy / Pydantic，React / TypeScript / Vite / TradingView Lightweight Charts 5。无需 MySQL、Redis、Docker 或任何账户；获取真实行情需要联网，已有行情可离线研究。

## 快速启动

要求 Python 3.12+、Node.js 20.19+ 或 22.12+、npm。以下脚本适用于 macOS / Linux。

```bash
# 在项目根目录
./scripts/setup.sh
./scripts/start.sh
```

系统 Python 较旧时：

```bash
PYTHON_BIN=/path/to/python3.12 ./scripts/setup.sh
```

打开 **http://localhost:5173**。后端 **http://localhost:8000**，交互式接口文档 **http://localhost:8000/docs**。Ctrl+C 同时停止前后端。启动脚本会检查端口占用，不会结束其他程序。

数据库在后端首次启动时自动创建，默认 `data/trading.duckdb`，无需手工建表。后台只运行一个 Uvicorn 进程，禁止用多个 worker 同时写 DuckDB。每次数据库操作受进程内锁保护，连接自动关闭，行情和整次回测均使用事务写入。

如需分别启动：

```bash
# 终端 1，项目根目录
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 终端 2
cd frontend
npm run dev
```

Windows 可用 `py -3.12 -m venv .venv`、`.venv\Scripts\python -m pip install -e "./backend[dev]"` 与 `npm --prefix frontend ci` 安装，再在两个终端分别启动 Uvicorn 和 Vite。锁文件中的 uvloop 仅适用于 macOS/Linux。

## 第一次研究

1. 输入 `000938`，选择过去五年，复权方式选「前复权」。
2. 默认使用「东方财富 / AKShare」，点击「下载历史」。若该源在当前网络受限，明确选择「腾讯行情 · 备用数据源」再下载。不同来源分别存储，不会自动拼接。
3. 行情加载后同时显示交互式日 K、均线、成交量、MACD；时间轴共享，可滚轮缩放和拖动。
4. 选择「均线金叉」或「MACD 基础策略」，修改参数与「撮合设置」，点击「运行回测」。
5. 图表显示**实际成交日**的 BUY/SELL 箭头和持仓区间；点击箭头显示成交价、信号日、策略及原因。
6. 点击下方任意 Trade 行（也支持键盘 Enter/空格），图表定位到入场前 10 根、持仓期间、离场后 10 根。该笔交易高亮，仍可继续缩放/拖动，「显示全部」复位。
7. 查看收益、回撤、胜率、完整交易数、每日权益和回撤曲线。期末未平仓单独显示。
8. 后续点击「增量更新」获取本地最后交易日之后的数据；重启后点击「读取本地」即可打开缓存。
9. 右上角「历史回测记录」恢复之前的参数、费用、行情快照和结果。刷新行情不会改变历史回测。

还提供显著标记的「模拟数据 · 离线验证」模式，用于无网络时验证整个软件闭环。它是确定性合成数据，不是真实历史；来源始终为 `sample`，不会替代或覆盖真实行情。

## 模块

```text
backend/app/
  data/          BaseMarketDataProvider、EastMoney、Tencent、Sample
  database/      DuckDB schema 与 Repository
  indicators/    IndicatorRegistry、SMA/EMA/MACD/RSI/BOLL/ATR/KDJ/Volume MA/slope
  strategies/    BaseStrategy、参数模型、MA/MACD 信号规则与注册表
  backtest/      纯撮合引擎、ExecutionPolicy、费用、统计
  models/        Pydantic 请求与配置验证
  services/      下载/增量/复权校验、研究流程、JSON 序列化
  api/           REST 路由
  main.py        FastAPI 应用工厂、生命周期、异常处理
backend/tests/   指标、因果性、撮合、数据库、数据源、API 测试
frontend/src/
  charts/        日 K + 共享时间轴 panes、持仓覆盖层、权益与回撤
  components/    统计卡、Trade Table
  pages/         研究工作台与状态管理
  services/      API 客户端
  types/         API 数据类型
scripts/         安装、启动、验证
data/            本地数据库（不提交 Git）
```

策略不访问数据库；指标不依赖策略；前端不计算指标、信号或回测。Provider 是行情来源的唯一入口，AKShare 仅由 EastMoneyProvider 导入。EastMoney 使用 AKShare，在请求格式不兼容时尝试同源日 K 接口；TencentProvider 是独立的显式备用选项。

## 行情及复权

`daily_bars` 主键为 `(symbol, date, adjust_type, data_source)`，支持 `raw/qfq/hfq` 共存。保存 OHLC、volume、amount、turnover、pre_close、change、pct_change、来源、更新时间。股票代码始终是字符串，保留前导零。

- 成交量统一为**股**，成交额为**元**，换手率/涨跌幅使用百分数值（例如 `1.2` 表示 `1.2%`）。
- 东方财富提供完整字段。腾讯备用日 K 通道只提供 OHLCV；缺失 amount/turnover 保存为 NULL，不伪造。腾讯 pre_close/change/pct_change 由同次请求的相邻收盘计算，第一条为空。
- 初始化下载所选区间，普通增量仅从本地最后日期 + 1 天开始。无新数据时返回明确消息。补充更早历史请用「下载历史」，不是「增量更新」。
- 对真实复权行情，写入新数据前会额外请求**一根已存储的历史锚点**校验价格。若基准变化，返回 409，拒绝拼接不同复权基准。这是常规增量的一次小校验，不重新下载多年数据。
- 「完整刷新」会原子替换所选范围与当前同来源/同复权缓存范围的并集；失败时不清空旧数据。锚点检验无法覆盖所有供应商的局部历史修订，严肃研究前可主动完整刷新。
- 腾讯接口可能截断长范围请求，因此 Provider 按年分页；每页仍受所选起止日期约束。
- 非交易日不会补出虚构 K 线；模拟数据只按工作日生成，不使用交易所节假日日历。
- 在收盘后下载当日日 K；上游可能返回盘中未定稿行情，V0.1 尚无交易所日历与实时收盘状态校验。

## 回测口径

| 项目 | V0.1 行为 |
|---|---|
| 方向/仓位 | 单股票、只做多、尽可能满仓买入、全部卖出 |
| 信号 | 收盘后确认，逐日输出 BUY/SELL/HOLD/NONE、position_target、reason |
| 成交 | `signal_at_close` + `execute_next_open`，最后一日信号无未来开盘则不成交 |
| 买入 | `open × (1 + slippage)`，100 股整数倍，先预留佣金 |
| 卖出 | `open × (1 - slippage)`，扣佣金及卖出印花税 |
| 佣金 | `max(notional × commission_rate, minimum_commission)`，按分四舍五入 |
| 印花税 | `sell_notional × stamp_tax_rate`，按分四舍五入，仅卖出收取 |
| 停牌 | volume=0 不成交，待执行信号延后；相反新信号会覆盖原指令 |
| 资金不足 | 拒绝该买入信号并保存原因，不出现负现金或零股成交 |
| T+1 | 买入开盘后最早次日开盘卖出；不支持同日买卖 |
| 期末仓位 | 不强制平仓，计入 final_equity，单列 open_position |
| 指标预热 | 从所选区间起点开始；SMA/EMA/MACD 未成熟部分为空，不倒填 |
| MACD 柱 | `2 × (DIF - DEA)`；EMA adjust=False |
| RSI/ATR | Wilder alpha=1/N 的递推平滑，以首个可用值初始化 |
| slope | `(series[t] - series[t-N]) / N`，N>0 |

指标计算和内置策略通过“完整序列与历史前缀结果一致”的测试，避免内置未来数据泄漏。自定义插件仍需遵守因果约束，引擎不会自动证明任意 Python 策略无未来函数。

统计定义：

- 总收益 = 期末权益 / 初始资金 - 1。每日权益 = 现金 + 股数 × 当日收盘价。
- 年化 = `(final_equity / initial_cash) ** (252 / K线数量) - 1`。短样本可能产生很大年化，溢出时返回 NULL。
- 最大回撤 = 每日权益 / 从初始资金开始累计最高权益 - 1 的最小值，采用负数表示。
- Trade profit = 卖出金额 - 买入金额 - 双边佣金 - 印花税；net_return = profit / (买入金额 + 买入佣金)。
- gross_return = 卖出成交价 / 买入成交价 - 1（价格已含滑点）。
- 胜率、平均交易收益、最好/最差交易、连续胜负均只基于已平仓 Trade。盈亏比 = 平均盈利金额 / 平均亏损金额绝对值；没有盈利或亏损样本时为 NULL。
- holding_days 使用自然日差，另保存 holding_bars 交易 K 线数量差。
- MFE / MAE 使用实际持仓期间日高/低相对成交买价的最大有利/不利幅度（零为基准）；卖出日仅使用开盘成交价，不包含卖出之后的高低价。它们是税费前价格幅度。
- max_profit_during_trade = MFE；max_drawdown_during_trade 是从买入价开始、持仓每日收盘与卖出成交价序列的最大回撤，不假设日内高低发生顺序。

默认参数是可配置的研究假设，不是历史费率数据库。V0.1 不按历史日期切换印花税，不单列过户费，不核算分红送转、融资融券、涨跌停封单、市场冲击或各板块特殊委托门槛。复权价格直接用于研究撮合，因此不是完整的真实现金分红与股数变化账本。`ExecutionPolicy.can_execute(bar, side)` 已预留涨跌停/板块限制接口。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 服务状态 |
| GET | `/api/config` | 后端默认撮合参数（包括 .env 配置） |
| GET | `/api/stocks` | 本地缓存范围，按来源/复权筛选 |
| GET | `/api/stocks/{symbol}/bars` | 历史 K 线与图表指标 |
| POST | `/api/data/download` | 初始化或完整刷新 |
| POST | `/api/data/update` | 增量更新 |
| GET | `/api/strategies` | 策略及参数 JSON Schema |
| GET | `/api/indicators` | 指标注册表 |
| POST | `/api/backtest` | 回测并原子保存 |
| GET | `/api/backtest` | 最近 100 次运行 |
| GET | `/api/backtest/{run_id}` | 包含行情/参数的不可变快照 |
| GET | `/api/backtest/{run_id}/trades` | 逐笔交易 |
| GET | `/api/backtest/{run_id}/equity` | 每日权益与回撤 |

请求示例：

```bash
curl -X POST http://localhost:8000/api/data/download \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"000938","start_date":"2021-09-19","end_date":"2026-09-19","adjust":"qfq","source":"eastmoney"}'

curl -X POST http://localhost:8000/api/backtest \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"000938","start_date":"2021-09-19","end_date":"2026-09-19","adjust":"qfq","source":"eastmoney","strategy_name":"ma_cross","parameters":{"fast_ma":5,"slow_ma":20},"config":{"initial_cash":100000,"commission_rate":0.0003,"minimum_commission":5,"stamp_tax_rate":0.0005,"slippage":0.001}}'
```

时间范围无本地数据/参数错误返回 422；上游失败或无行情返回 502；复权校验失败返回 409；不存在的运行返回 404。前端保留界面并显示中文原因。

`strategy_runs` 保存版本、参数、配置、数据 SHA-256 与完整结果快照；`signals`、`trades`、`equity_curve` 同时独立存储，Trade 完整字段位于 `trades.payload` JSON。没有覆盖历史回测的接口。

## 添加策略或指标

现在可以在「策略配置」使用 **Python / 文件策略** 创建自己的策略，也可以在 VS Code 编辑 `strategy/` 文件。内置 MA/MACD 仍保留。旧规则策略仍可从策略库删除，已有历史回测仍可查看。

### 使用 Python 编辑器

也可以在 VS Code 中编辑项目根目录的 `strategy/` 文件夹。每个策略放一个 `.py` 文件，定义 `generate_signals(data, params)`；例如现有的 `strategy/strategy_gpt.py`。在网页切换到「Python / 文件策略」，通过「VS Code 文件策略」选择文件，然后直接校验或运行回测。新增文件后点击「刷新文件列表与预览」。修改已选文件并保存后，下次校验或回测会读取最新代码，无需重新粘贴或保存到数据库；代码预览可手动刷新。文件里的 `DEFAULT_PARAMS` 等默认值由策略代码自行处理，网页传入空的 `params` 字典。历史回测会保存当次执行的完整源码快照，之后修改文件不会改变旧结果。

点击「保存文件到策略库」会把当前磁盘代码保存为可选择、可删除的版本；同一文件可继续点击「保存文件新版本」。库中保存的是当时的代码副本，重新选择后会载入在线编辑器。要继续运行文件的最新修改，请选择原文件。删除库中版本不会删除 `.py` 源文件。

卖出点研究见 [分段保护退出与完整对照](examples/000938_exit_research/README.md)：保留原买点，量化高点回吐、退出滞后、卖早损失，并展示同业反证。

针对000938的研究候选见 [波段启动策略与买点评估](examples/000938_swing/README.md)，含可编辑源码、完整买点清单、失败案例和复现脚本。

入门学习见 [Python 策略学习说明](examples/python_strategy_learning/README.md)，附带可直接粘贴的 [18 参数示例函数](examples/python_strategy_learning/strategy.py) 和 [参数文件](examples/python_strategy_learning/parameters.json)，说明输入数据、输出信号、保存位置及本地文件调用方式。

1. 切换到「Python 编辑器」，点击载入「均线金叉」或「DIF 斜率拐头」示例（会替换当前编辑区）。
2. 修改买入/卖出条件或下面的数值参数；可以回车新增参数名称。示例代码保留了输出结构，不需继承类或修改系统目录。
3. 点击「校验策略与信号」；语法、运行错误会显示代码行号，错误的日期/信号/仓位/原因字段也会被拒绝。
4. 校验通过后保存并回测。直接回测也会执行同样的检查。

固定接口：

```python
def generate_signals(data, params):
    # data: 已按日期排序的 Pandas DataFrame，包括 OHLCV 和标准图表指标
    # params: 编辑区配置的数值参数字典
    # 返回 DataFrame，必须与 data 日期、行数一一对应：
    # date / signal / position_target / reason
    # signal = BUY / SELL / HOLD / NONE
    # position_target = 0 或 1，reason 为非空字符串
    ...
```

完整可运行代码见界面示例或 `backend/app/strategies/templates.py`。可以导入 `app.indicators.technical` 的指标函数以及已安装的 Pandas/NumPy。未成熟指标为 NaN，应返回 NONE 而不是删除这些日期。HOLD 对应目标仓位 1，NONE 对应 0。目标仓位不等于已撮合持仓：资金不足/停牌可能导致信号未成交。

Python 在临时工作目录中的独立进程执行，总超时 15 秒（含校验），不会把代码拼接成 shell 命令。保存版本只检查语法与入口，不执行代码。执行时会抽查中点及末日前的两段历史前缀，若信号/原因随未来数据改变则拒绝；这能发现常见未来函数或随机状态问题，不构成对任意 Python 的严格证明。自定义代码只返回信号，图表仍使用标准图表指标。

**这是可信本机代码入口，不是安全沙箱**：代码拥有当前用户的文件与网络权限，只运行自己信任的代码，不要将该服务暴露到公网。API 限制本地主机名与浏览器来源；子进程/超时主要用于隔离策略错误和死循环。

### 草稿、保存与历史版本

- 两个编辑器草稿独立，自动保存在当前浏览器的 localStorage；不同浏览器或端口不共享草稿。
- 「保存策略」写入 DuckDB 的 `strategy_definitions`；之后「保存新版本」追加 V2/V3，不覆盖旧版本。「另存为新策略」创建新系列。
- 在已保存策略下拉框选中版本后立即载入，可直接运行回测。只保存并不意味着策略已通过行情校验。
- 每次回测都嵌入完整规则或 Python 源码、参数、说明和内容 SHA-256。右上角历史回测恢复当次编辑内容；后续编辑不会改动已有结果。由回测快照恢复的内容可另存为策略；若要延续已有版本系列，请从策略版本列表加载。
- 自定义策略的 `strategy_version` 为完整定义的 SHA-256，内置策略仍使用语义版本。

新增 API：`GET /api/strategy-editor/examples`、`GET /api/strategy-editor/files`、`GET /api/strategy-editor/files/{filename}`、`GET/POST /api/strategy-editor/definitions`、`GET /api/strategy-editor/definitions/{id}`、`POST /api/strategy-editor/validate`。`POST /api/backtest` 和校验接口可传 `strategy_file`（文件名）以运行 `strategy/` 中的最新代码；与 `custom_strategy` 二选一。不传这两个字段时保持内置策略行为。

### 扩展系统级插件

1. 在 `backend/app/strategies/` 新建类，继承 `BaseStrategy`，指定唯一 name、label、version、Pydantic parameter_model。
2. `prepare(data, params)` 通过独立指标模块增加需要的列。
3. `generate_signals(data, params)` 返回与行情日期逐行对齐的 DataFrame，包含 `date, signal, position_target, reason`。第一版 position_target 仅 0/1，BUY/SELL 是执行指令，HOLD/NONE 不创建新订单。
4. 在 `strategies/__init__.py` 导入并调用 `register_strategy(MyStrategy())`；前端从 API 读取策略及整数参数，不需修改策略计算代码。
5. 增加前缀一致性测试，运行 `./scripts/check.sh`。目前参数编辑器面向数值/整数参数；新增字符串/枚举参数时需扩展编辑器。

MACD 斜率策略可直接复用：

```python
from app.indicators.technical import calculate_macd, slope

def prepare(self, data, params):
    result = calculate_macd(data, fast=12, slow=26, signal=9)
    result["dif_slope"] = slope(result.macd_dif, params["period"])
    result["dea_slope"] = slope(result.macd_dea, params["period"])
    return result
```

自定义指标调用 `IndicatorRegistry.register("NAME", function)`，函数接收 DataFrame 和参数并返回新 DataFrame。新增行情源继承 `BaseMarketDataProvider`，在 MarketService 的 provider 字典注册，同时更新 API Source 枚举和前端来源列表。

## 配置、测试与排错

可复制 `.env.example` 为 `.env`，修改 DATABASE_PATH、API_PORT、FRONTEND_PORT、DEFAULT_COMMISSION、LOG_LEVEL。相对数据库路径始终相对项目根目录。前端通过 Vite 代理访问后端。只监听 127.0.0.1，适合本机研究。

```bash
./scripts/check.sh
# 单独运行
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
```

测试不请求真实外网；使用隔离的临时 DuckDB。覆盖指标参考计算、因果性、参数验证、整手买入、次日撮合、滑点、最低佣金、卖出税、收益/回撤、交易生成、期末持仓、停牌、资金不足、重复写入、来源/复权隔离、增量范围、复权基准变化、API 及历史快照。

真实行情源不可用时检查网络/代理，或切换腾讯源；不需要重装数据库。启动时端口占用请关闭先前启动终端或在 `.env` 改端口。DuckDB 锁冲突通常是同时启动了多个后端进程。后端日志包含下载、写入、回测起止和异常。

依赖由 `backend/requirements.lock` 与 `frontend/package-lock.json` 固定；有意升级依赖后应重新执行全部测试与浏览器验收。

参考：[AKShare 股票数据文档](https://akshare.akfamily.xyz/data/stock/stock.html)、[Lightweight Charts panes](https://tradingview.github.io/lightweight-charts/tutorials/how_to/panes)、[TradingView](https://www.tradingview.com/)。Lightweight Charts 为 Apache-2.0 项目，界面保留归属链接及库自带归属展示。
# Trading_backtest_system

## 实验记录管理

工作台右上角点击「实验记录管理」，可以查看全部历史实验（每页 20 条）、恢复回测快照、收藏与清理记录。

- 单条删除：点击实验右侧垃圾桶，在确认框核对股票、策略、创建时间与实验编号后确认。
- 批量删除：勾选记录或选择本页未收藏实验，再点击「删除所选」。切换页面、筛选或刷新后会清空选择，避免误删隐藏记录。
- 收藏：点击星标保存重要实验，「只看收藏」可快速查找。收藏状态持久保存，独立于原始快照。已收藏实验禁止删除，需先取消收藏；后端也会在删除时重新检查收藏状态。
- 空间：顶部显示 DuckDB 文件与 WAL 日志的实际字节数、实验快照总大小和实验数量；每条记录显示快照大小。快照大小按已保存 JSON 的 UTF-8 字节数计算，是未压缩逻辑大小，不等于压缩后占用的磁盘空间，也不包含另外存储的信号、交易、资金曲线表和索引。

删除是不可撤销操作，会在同一事务内清理实验快照及对应的信号、交易明细、资金曲线和收藏元数据；失败会全部回滚。共享行情及独立保存的策略版本不会被删除。DuckDB 文件删除记录后可能不会立即缩小，空出的空间可用于后续写入；界面不会将快照字节数当作实际释放空间。

管理接口：`GET /api/experiments?page=1&page_size=20&favorites=false`（返回分页列表和整体空间统计）；`POST /api/experiments/{run_id}/favorite` 接收 `{"is_favorite": true}`；`POST /api/experiments/delete` 接收 `{"run_ids": ["实验编号"]}`，最多 100 条，返回已删除、受收藏保护和不存在的编号。原有历史回测接口保持兼容。旧数据库启动时自动增加收藏元数据表，无需重建或迁移原始快照。

## 自选股与每日行情更新

行情独立于回测结果持久保存在 `data/trading.duckdb`，按股票代码、数据源、复权方式隔离。左侧「自选股」直接读取已有行情库，旧数据无需重新下载；输入新股票代码并「下载历史」后自动加入。每只股票默认只显示名称和代码，点击后展开已保存版本、日 K 数量、历史范围和更新状态；同一时间只展开一只。收起整个侧栏后重新打开，或刷新页面，股票详情均恢复收起。真实股票名称后台自动补充并保存在本地，后续行情写入不会覆盖名称。点击行情版本会读取该股票全部已保存历史，保留当前内置策略参数或规则/Python 草稿，清空上一只股票的回测显示；同一策略可以直接用于不同股票。

侧栏箭头可收起/展开，浏览器会记住收起状态。可搜索名称或代码，展开后点击单只股票的刷新按钮或「全部增量更新」补齐最近行情。侧栏更新按钮面向最近已结束的更新日期，不受右侧历史研究区间限制；原有右侧「增量更新」仍以所选结束日期为准。

「每天自动更新」默认开启，设置保存在数据库中。北京时间每天 18:00 更新，服务启动时检查上一次应更新日期，18:00 前不请求当天未确认的日线，周末沿用最近周五。仅更新真实数据源，不自动延长模拟行情。后台每分钟检查是否到期；已覆盖该日期的版本不会重复请求，网络失败或暂无新行情每小时重试，也可立即手动重试。节假日和停牌以数据源是否返回新行情为准，暂无行情不会被显示成已更新至当天。复权基准变化时停止追加并提示「完整刷新」，避免混用价格基准。

自动更新需要本地后端服务持续运行；关闭网页不会停止更新，电脑休眠或服务关闭时暂停，重新启动后补查。更新某份行情失败不影响其他股票，已有行情和历史回测快照保留。页面每 15 秒刷新侧栏状态；点击股票即可加载更新后的行情，正在查看的历史回测快照不会被后台替换。

接口：`GET /api/watchlist` 返回全部已保存行情版本和更新状态；`POST /api/watchlist/settings` 接收 `{"enabled": true}`；`POST /api/watchlist/update` 接收 `{}` 更新全部，或 `{"symbol": "000938"}` 更新该股票的全部真实行情版本。已有 `/api/stocks` 和下载、回测接口保持兼容。

打开工作台或从侧栏切换股票时，默认选择本地行情最新的真实数据源；有当前复权版本时保持该复权方式，日期相同时优先更新正常的来源。来源仍可手动选择，展开详情或查看历史回测不会自动改写已选来源。

## 策略编辑与策略管理

Python 策略默认以紧凑摘要显示，保留名称、版本状态、已保存策略选择和「编辑策略」入口。选中策略即载入并可直接运行回测；点击「编辑策略」展开代码、参数、校验和保存操作。收起编辑器保留草稿，切换编辑模式或恢复历史回测时默认重新收起。

点击页面上方「实验记录管理」旁的「策略管理」，查看所有已保存版本，每行显示名称、版本、类型和保存时间。可勾选多行或全选，点击「删除所选」并确认。网页编辑和文件策略保存的版本都在此管理，旧规则版本也可清理。删除会同步更新策略下拉列表，当前代码保留为草稿；源文件、行情和历史回测快照保留。内置策略不支持删除。数据库采用删除标记保留版本序号，不会重新使用已删除的版本号。批量删除接口为 `POST /api/strategy-editor/definitions/delete`，接收 `definition_ids`，返回已删除和已不存在的 ID；原单版本删除接口保留兼容。
