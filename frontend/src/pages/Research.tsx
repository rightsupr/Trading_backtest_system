import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ChartCandlestick,
  ChevronDown,
  Database,
  FlaskConical,
  History,
  Play,
  RefreshCw,
  Settings2,
} from "lucide-react";
import PriceChart from "../charts/PriceChart";
import EquityChart from "../charts/EquityChart";
import Metrics from "../components/Metrics";
import TradeTable from "../components/TradeTable";
import { api, money, percent } from "../services/api";
import type {
  Bar,
  Config,
  Fill,
  Query,
  Run,
  RunSummary,
  Strategy,
  Trade,
} from "../types";

const today = new Date();
const isoDate = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const fiveYearsAgo = new Date(
  today.getFullYear() - 5,
  today.getMonth(),
  today.getDate(),
);
const defaultQuery: Query = {
  symbol: "000938",
  start_date: isoDate(fiveYearsAgo),
  end_date: isoDate(today),
  source: "eastmoney",
  adjust: "qfq",
};
const defaultConfig: Config = {
  initial_cash: 100000,
  commission_rate: 0.0003,
  minimum_commission: 5,
  stamp_tax_rate: 0.0005,
  slippage: 0.001,
};

export default function Research() {
  const chartPanel = useRef<HTMLElement>(null);
  const [query, setQuery] = useState<Query>(defaultQuery);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategy, setStrategy] = useState("ma_cross");
  const [parameters, setParameters] = useState<Record<string, number>>({
    fast_ma: 5,
    slow_ma: 20,
  });
  const [config, setConfig] = useState<Config>(defaultConfig);
  const [bars, setBars] = useState<Bar[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<Trade | null>(null);
  const [fill, setFill] = useState<Fill | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("准备就绪 · 选择数据范围，开始你的研究");
  const [advanced, setAdvanced] = useState(false);
  const [online, setOnline] = useState(false);

  useEffect(() => {
    Promise.all([
      api<Strategy[]>("/strategies"),
      api<RunSummary[]>("/backtest"),
      api<Config>("/config"),
    ])
      .then(([s, h, c]) => {
        setStrategies(s);
        setHistory(h);
        setConfig(c);
        setOnline(true);
      })
      .catch((e) => setError(e.message));
  }, []);

  const clearRun = () => {
    setRun(null);
    setSelected(null);
    setFill(null);
  };
  const updateQuery = (patch: Partial<Query>) => {
    setQuery({ ...query, ...patch });
    setBars([]);
    clearRun();
    setNotice("查询条件已更改，请加载本地数据或下载历史");
  };
  const work = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    setError("");
    try {
      await action();
      setOnline(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy("");
    }
  };
  const loadBars = async (q = query) => {
    const { bars: next } = await api<{ bars: Bar[] }>(
      `/stocks/${q.symbol}/bars?${new URLSearchParams({ start_date: q.start_date, end_date: q.end_date, adjust: q.adjust, source: q.source })}`,
    );
    setBars(next);
    clearRun();
    if (!next.length) setNotice("本地尚无此范围的行情，请点击「下载历史」");
    return next;
  };
  const download = (kind: "download" | "update", refresh = false) =>
    work(
      refresh
        ? "正在刷新完整历史…"
        : kind === "update"
          ? "正在增量更新…"
          : "正在下载历史行情…",
      async () => {
        const result = await api<{ message: string }>(`/data/${kind}`, {
          ...query,
          force_refresh: refresh,
        });
        await loadBars();
        setNotice(result.message);
      },
    );
  const execute = () =>
    work("正在计算策略与回测…", async () => {
      const result = await api<Run>("/backtest", {
        ...query,
        strategy_name: strategy,
        parameters,
        config,
      });
      setRun(result);
      setSelected(null);
      setFill(null);
      setNotice(`回测完成 · ${result.trades.length} 笔完整交易 · 结果已保存`);
      setHistory(await api<RunSummary[]>("/backtest"));
    });
  const loadRun = (id: string) => {
    if (!id) return;
    void work("正在读取回测快照…", async () => {
      const result = await api<Run>(`/backtest/${id}`);
      const r = result.request;
      setQuery({
        symbol: r.symbol,
        start_date: r.start_date,
        end_date: r.end_date,
        source: r.source,
        adjust: r.adjust,
      });
      setStrategy(r.strategy_name);
      setParameters(r.parameters);
      setConfig(r.config);
      setRun(result);
      setBars(result.bars);
      setSelected(null);
      setFill(null);
      setNotice(
        `历史回测 · ${new Date(result.created_at).toLocaleString("zh-CN")} · 使用保存的行情快照`,
      );
    });
  };
  const changeStrategy = (name: string) => {
    setStrategy(name);
    clearRun();
    const schema =
      strategies.find((s) => s.name === name)?.parameters.properties ?? {};
    setParameters(
      Object.fromEntries(
        Object.entries(schema).map(([key, value]) => [key, value.default]),
      ),
    );
  };
  const chartBars = run?.bars ?? bars;
  const chooseTrade = (trade: Trade) => {
    setSelected({ ...trade });
    setFill(null);
    chartPanel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const currentStrategy = strategies.find((s) => s.name === strategy);

  return (
    <>
      <header className="app-header">
        <div className="brand">
          <span className="brand-icon">
            <Activity size={23} />
          </span>
          <strong>
            研序<span>QUANT RESEARCH</span>
          </strong>
          <span className="version">V0.1</span>
        </div>
        <nav>
          <span className="nav-active">
            <FlaskConical size={16} /> 策略研究
          </span>
          <a href="/docs" target="_blank" rel="noopener">
            API 文档 <ArrowRight size={14} />
          </a>
        </nav>
        <div className="local-status">
          <i className={online ? "online" : ""} />
          {online ? "本地服务已连接" : "连接本地服务"}
          <span>LOCAL</span>
        </div>
      </header>
      <main>
        <div className="page-heading">
          <div>
            <div className="eyebrow">RESEARCH WORKSPACE</div>
            <h1>策略研究工作台</h1>
            <p>从行情到信号，从交易到洞察。</p>
          </div>
          <label className="history-select">
            <History size={16} />
            <select
              aria-label="历史回测"
              value={run?.run_id ?? ""}
              onChange={(e) => loadRun(e.target.value)}
              disabled={!!busy}
            >
              <option value="">历史回测记录</option>
              {history.map((h) => (
                <option key={h.run_id} value={h.run_id}>
                  {h.symbol} · {h.strategy_name} · {h.created_at.slice(0, 16)}
                </option>
              ))}
            </select>
            <ChevronDown size={13} />
          </label>
        </div>
        <section className="panel controls">
          <fieldset disabled={!!busy}>
            <div className="control-row market-controls">
              <label>
                股票代码
                <input
                  aria-label="股票代码"
                  value={query.symbol}
                  maxLength={6}
                  onChange={(e) => updateQuery({ symbol: e.target.value })}
                  className="symbol-input"
                />
              </label>
              <label>
                开始日期
                <input
                  aria-label="开始日期"
                  type="date"
                  value={query.start_date}
                  onChange={(e) => updateQuery({ start_date: e.target.value })}
                />
              </label>
              <span className="date-divider">—</span>
              <label>
                结束日期
                <input
                  aria-label="结束日期"
                  type="date"
                  value={query.end_date}
                  onChange={(e) => updateQuery({ end_date: e.target.value })}
                />
              </label>
              <label>
                数据源
                <select
                  aria-label="数据源"
                  value={query.source}
                  onChange={(e) =>
                    updateQuery({ source: e.target.value as Query["source"] })
                  }
                >
                  <option value="eastmoney">东方财富 / AKShare</option>
                  <option value="tencent">腾讯行情 · 备用数据源</option>
                  <option value="sample">模拟数据 · 离线验证</option>
                </select>
              </label>
              <label>
                复权方式
                <select
                  aria-label="复权方式"
                  value={query.adjust}
                  onChange={(e) =>
                    updateQuery({ adjust: e.target.value as Query["adjust"] })
                  }
                >
                  <option value="qfq">前复权</option>
                  <option value="raw">不复权</option>
                  <option value="hfq">后复权</option>
                </select>
              </label>
              <div className="data-buttons">
                <button onClick={() => download("download")}>
                  <ArrowDownToLine size={15} />
                  下载历史
                </button>
                <button
                  onClick={() => download("update")}
                  title="只下载最后一个本地交易日之后的数据"
                >
                  <RefreshCw size={14} />
                  增量更新
                </button>
              </div>
            </div>
            <div className="control-row strategy-controls">
              <span className="section-label">
                <FlaskConical size={17} />
                策略配置
              </span>
              <label className="inline-label">
                <select
                  aria-label="策略"
                  value={strategy}
                  onChange={(e) => changeStrategy(e.target.value)}
                >
                  {strategies.length ? (
                    strategies.map((s) => (
                      <option key={s.name} value={s.name}>
                        {s.label}
                      </option>
                    ))
                  ) : (
                    <option value="ma_cross">均线金叉</option>
                  )}
                </select>
              </label>
              {Object.entries(parameters).map(([key, value]) => (
                <label className="parameter" key={key}>
                  {key}
                  <input
                    aria-label={key}
                    type="number"
                    min={
                      currentStrategy?.parameters.properties[key]?.minimum ?? 1
                    }
                    max={
                      currentStrategy?.parameters.properties[key]?.maximum ??
                      500
                    }
                    step="1"
                    value={value}
                    onChange={(e) => {
                      setParameters({
                        ...parameters,
                        [key]: Number(e.target.value),
                      });
                      clearRun();
                    }}
                  />
                </label>
              ))}
              <button
                className={`text-button settings-toggle ${advanced ? "active" : ""}`}
                onClick={() => setAdvanced(!advanced)}
              >
                <Settings2 size={15} />
                撮合设置
              </button>
              <span className="execution-badge">
                收盘信号 <ArrowRight size={12} /> 次日开盘
              </span>
              <button
                className="primary run-button"
                onClick={execute}
                disabled={!chartBars.length || !!busy}
              >
                <Play size={15} fill="currentColor" />
                运行回测
              </button>
            </div>
            {advanced && (
              <div className="advanced-settings">
                {Object.entries(config)
                  .filter(([key]) => key in defaultConfig)
                  .map(([key, value]) => (
                    <label key={key}>
                      {
                        (
                          {
                            initial_cash: "初始资金 / 元",
                            commission_rate: "佣金率",
                            minimum_commission: "最低佣金 / 元",
                            stamp_tax_rate: "卖出印花税率",
                            slippage: "滑点比例",
                          } as Record<string, string>
                        )[key]
                      }
                      <input
                        type="number"
                        step="any"
                        min="0"
                        value={value}
                        onChange={(e) => {
                          setConfig({
                            ...config,
                            [key]: Number(e.target.value),
                          });
                          clearRun();
                        }}
                      />
                    </label>
                  ))}
              </div>
            )}
          </fieldset>
          <div className="data-footer">
            <span>
              <Database size={12} />
              {chartBars.length
                ? `${chartBars.length.toLocaleString()} 根日 K · ${chartBars[0].date} — ${chartBars.at(-1)?.date}`
                : "DuckDB 本地行情库"}
            </span>
            <div>
              <button
                className="text-button"
                disabled={!!busy}
                onClick={() =>
                  work("正在读取本地行情…", async () => {
                    const b = await loadBars();
                    if (b.length) setNotice(`已读取 ${b.length} 根本地日 K`);
                  })
                }
              >
                读取本地
              </button>
              <button
                className="text-button"
                disabled={!!busy}
                title="重新获取所选范围和已有缓存的完整历史"
                onClick={() => download("download", true)}
              >
                完整刷新
              </button>
            </div>
          </div>
        </section>
        {query.source === "sample" && (
          <div className="sample-banner">
            模拟数据模式：当前价格与交易结果由合成行情生成，仅供验证软件功能，不代表真实股票表现。
          </div>
        )}
        <div
          className={`status-line ${error ? "error" : ""}`}
          role={error ? "alert" : "status"}
        >
          {busy ? (
            <>
              <RefreshCw size={13} className="spinning" />
              {busy}
            </>
          ) : (
            <>
              <span className="status-dot" />
              {error || notice}
            </>
          )}
        </div>
        <Metrics run={run} />
        <section className="panel chart-panel" ref={chartPanel}>
          <div className="panel-heading">
            <div className="panel-title">
              <ChartCandlestick size={18} />
              <h2>
                {query.symbol} <span>日线行情</span>
              </h2>
              <span className="pill">
                {query.adjust === "raw"
                  ? "不复权"
                  : query.adjust === "qfq"
                    ? "前复权"
                    : "后复权"}
              </span>
            </div>
            <div className="chart-key">
              <span>
                <i className="key-holding" />
                持仓区间
              </span>
              <span className="positive">▲ BUY</span>
              <span className="negative">▼ SELL</span>
            </div>
          </div>
          <PriceChart
            bars={chartBars}
            run={run}
            selected={selected}
            onSelect={chooseTrade}
            onFill={setFill}
          />
          <div className="chart-footer">
            <span>滚轮缩放 · 拖动平移 · 点击买卖箭头查看原因</span>
            <a
              href="https://www.tradingview.com/"
              target="_blank"
              rel="noreferrer"
            >
              Charts by TradingView
            </a>
          </div>
        </section>
        {fill && (
          <div className="fill-detail">
            <strong>
              {fill.side} · {fill.date}
            </strong>
            <span>成交价 ¥{fill.price.toFixed(3)}</span>
            <span>
              {currentStrategy?.label} · {fill.reason}
            </span>
            <span>信号日 {fill.signal_date}</span>
          </div>
        )}
        {selected && (
          <section className="trade-detail">
            <span className="detail-number">
              TRADE{" "}
              {String(
                (run?.trades.findIndex(
                  (t) => t.trade_id === selected.trade_id,
                ) ?? 0) + 1,
              ).padStart(2, "0")}
            </span>
            <div>
              <strong>
                {selected.entry_date} <ArrowRight size={13} />{" "}
                {selected.exit_date}
              </strong>
              <p>
                买入：{selected.entry_reason} · 卖出：{selected.exit_reason}
              </p>
            </div>
            <div>
              <strong
                className={selected.net_return >= 0 ? "positive" : "negative"}
              >
                {percent(selected.net_return)}
              </strong>
              <p>
                净收益 · 佣金 ¥{money(selected.commission)} · 税 ¥
                {money(selected.tax)}
              </p>
            </div>
            <span className="pill">已定位前后各 10 根 K 线</span>
          </section>
        )}
        <section className="panel equity-panel">
          <div className="panel-heading">
            <div className="panel-title">
              <Activity size={17} />
              <h2>
                资金表现 <span>Equity & Drawdown</span>
              </h2>
            </div>
            <span className="equity-summary">
              初始 ¥{money(run?.metrics.initial_cash ?? config.initial_cash)}
              <ArrowRight size={13} />
              期末 {run ? `¥${money(run.metrics.final_equity ?? 0)}` : "—"}
            </span>
          </div>
          {run ? (
            <EquityChart data={run.equity} />
          ) : (
            <div className="equity-empty">
              运行策略后，查看每日权益与回撤曲线
            </div>
          )}
          {run?.open_position && (
            <div className="open-position">
              期末持仓：{run.open_position.shares.toLocaleString()} 股 · 买入日{" "}
              {run.open_position.entry_date} · 浮动盈亏 ¥
              {money(run.open_position.unrealized_profit)}
              （已含买入佣金，未计假设卖出费用）
            </div>
          )}
        </section>
        <section className="panel trades-panel">
          <div className="panel-heading">
            <div className="panel-title">
              <h2>交易复盘</h2>
              <span className="count-badge">{run?.trades.length ?? 0}</span>
              <span className="muted">Trade List</span>
            </div>
            <span className="table-hint">
              点击任意交易，定位对应 K 线 <ArrowRight size={14} />
            </span>
          </div>
          <TradeTable
            trades={run?.trades ?? []}
            selected={selected}
            onSelect={chooseTrade}
          />
        </section>
        {run && (
          <details className="run-details">
            <summary>
              回测口径与运行信息 <span>{run.run_id.slice(0, 8)}</span>
            </summary>
            <p>{run.warnings.join(" ")}</p>
            <p>
              策略版本 {run.strategy_version} · 数据校验{" "}
              {run.data_hash.slice(0, 16)} · {run.rejected_orders.length}{" "}
              次未成交订单
            </p>
            {run.rejected_orders.slice(0, 20).map((r, i) => (
              <p key={i}>
                {r.date} · {r.side} · {r.reason}
              </p>
            ))}
          </details>
        )}
        <footer className="app-footer">
          <span>
            研序 QUANT RESEARCH <b> / </b> 本地研究，独立判断。
          </span>
          <span>
            A 股 · 单标的 · 日线回测 <i /> V0.1
          </span>
        </footer>
      </main>
    </>
  );
}
