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
