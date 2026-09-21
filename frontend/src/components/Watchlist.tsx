import { useState } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Star,
} from "lucide-react";
import type { Query, SavedStock, WatchlistData } from "../types";
import { chooseSavedStock } from "../services/stockSelection";

const sources = { eastmoney: "东方财富", tencent: "腾讯", sample: "模拟" };
const adjustments = { qfq: "前复权", hfq: "后复权", raw: "不复权" };
const stockName = (series: SavedStock[]) =>
  series.find((s) => s.name && s.name !== s.symbol)?.name ??
  (series.every((s) => s.source === "sample") ? "模拟股票" : "名称待补充");

export default function Watchlist({
  data,
  query,
  disabled,
  onSelect,
  onUpdate,
  onToggle,
  onRefresh,
}: {
  data: WatchlistData | null;
  query: Query;
  disabled: boolean;
  onSelect: (stock: SavedStock) => void;
  onUpdate: (symbol?: string) => void;
  onToggle: (enabled: boolean) => void;
  onRefresh: () => void;
}) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("quant.watchlist.collapsed") === "true";
    } catch {
      return false;
    }
  });
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const groups = new Map<string, SavedStock[]>();
  for (const stock of data?.stocks ?? []) {
    const list = groups.get(stock.symbol) ?? [];
    list.push(stock);
    groups.set(stock.symbol, list);
  }
  const toggle = () => {
    setExpanded(null);
    setCollapsed(!collapsed);
    try {
      localStorage.setItem("quant.watchlist.collapsed", String(!collapsed));
    } catch {
      /* optional preference */
    }
  };
  const visibleStocks = [...groups].filter(([symbol, series]) =>
    `${symbol} ${stockName(series)}`.includes(search.trim()),
  );
  const toggleStock = (symbol: string, series: SavedStock[]) => {
    if (expanded === symbol) {
      setExpanded(null);
      return;
    }
    setExpanded(symbol);
    if (query.symbol !== symbol) {
      const preferred = chooseSavedStock(series, query);
      if (preferred) onSelect(preferred);
    }
  };
  const updating = disabled || !!data?.running;
  return (
    <aside
      className={`watchlist ${collapsed ? "collapsed" : ""}`}
      aria-label="自选股"
    >
      <div className="watchlist-heading">
        {!collapsed && (
          <h2>
            <Star size={17} /> 自选股 <span>{groups.size}</span>
          </h2>
        )}
        <button
          className="watchlist-collapse"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-controls="watchlist-content"
          aria-label={collapsed ? "展开自选股" : "收起自选股"}
          title={collapsed ? "展开自选股" : "收起自选股"}
        >
          {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
        </button>
      </div>
      {collapsed ? (
        <span className="watchlist-rail">
          <Star size={17} />
          自选股<span>{groups.size}</span>
        </span>
      ) : (
        <div id="watchlist-content">
          <p className="watchlist-intro">点击股票切换研究、展开详情。</p>
          <input
            className="watchlist-search"
            aria-label="搜索自选股"
            placeholder="搜索名称或代码"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="watchlist-actions">
            <button
              disabled={
                updating || !data?.stocks.some((s) => s.source !== "sample")
              }
              onClick={() => onUpdate()}
            >
              <RefreshCw
                size={13}
                className={data?.running ? "spinning" : ""}
              />
              {data?.running ? "正在更新…" : "全部增量更新"}
            </button>
            <button
              title="刷新自选股列表"
              aria-label="刷新自选股列表"
              disabled={disabled}
              onClick={onRefresh}
            >
              <RefreshCw size={13} />
            </button>
          </div>
          <div className="watchlist-items">
            {!data && <p className="watchlist-empty">正在读取本地股票…</p>}
            {data && groups.size === 0 && (
              <p className="watchlist-empty">
                还没有保存的股票。
                <br />
                在右侧输入股票代码并下载历史，股票就会出现在这里。
              </p>
            )}
            {groups.size > 0 && visibleStocks.length === 0 && (
              <p className="watchlist-empty">没有匹配的股票</p>
            )}
            {visibleStocks.map(([symbol, series]) => (
              <div
                className={`watchlist-stock ${query.symbol === symbol ? "selected" : ""}`}
                key={symbol}
              >
                <button
                  className="watchlist-stock-toggle"
                  disabled={disabled}
                  aria-expanded={expanded === symbol}
                  aria-controls={`stock-details-${symbol}`}
                  onClick={() => toggleStock(symbol, series)}
                >
                  <span>
                    <strong>{stockName(series)}</strong>
                    <small>{symbol}</small>
                  </span>
                  <ChevronDown
                    size={15}
                    className={expanded === symbol ? "expanded" : ""}
                  />
                </button>
                {expanded === symbol && (
                  <div
                    id={`stock-details-${symbol}`}
                    className="watchlist-stock-details"
                  >
                    <div className="watchlist-stock-heading">
                      <span>已保存行情</span>
                      {series.some((s) => s.source !== "sample") && (
                        <button
                          disabled={updating}
                          aria-label={`增量更新 ${symbol}`}
                          title="更新这只股票的所有真实行情版本"
                          onClick={() => onUpdate(symbol)}
                        >
                          <RefreshCw size={13} />
                        </button>
                      )}
                    </div>
                    {series.map((stock) => (
                      <div key={`${stock.source}-${stock.adjust}`}>
                        <button
                          className={`watchlist-series ${query.symbol === symbol && query.source === stock.source && query.adjust === stock.adjust ? "active" : ""}`}
                          disabled={disabled}
                          onClick={() => onSelect(stock)}
                          aria-pressed={
                            query.symbol === symbol &&
                            query.source === stock.source &&
                            query.adjust === stock.adjust
                          }
                        >
                          <span>
                            {sources[stock.source]} ·{" "}
                            {adjustments[stock.adjust]}
                          </span>
                          <strong>{stock.bars.toLocaleString()} 根日 K</strong>
                          <small>
                            {stock.start_date} — {stock.end_date}
                          </small>
                        </button>
                        {stock.source === "sample" ? (
                          <p className="watchlist-note">
                            模拟数据 · 不自动更新
                          </p>
                        ) : (
                          <p
                            className={`watchlist-note ${stock.status === "error" || stock.status === "refresh_required" ? "failed" : ""}`}
                            title={stock.message ?? undefined}
                          >
                            {stock.status === "refresh_required"
                              ? "复权变化：请选中后完整刷新"
                              : stock.status === "error"
                                ? `更新失败：${stock.message}`
                                : stock.status === "waiting"
                                  ? "数据源暂无新行情，可稍后重试"
                                  : stock.end_date >= (data?.target_date ?? "")
                                    ? "已覆盖最近应更新日期"
                                    : "待增量更新"}
                            {stock.checked_at && (
                              <small>
                                检查于{" "}
                                {new Date(stock.checked_at).toLocaleString(
                                  "zh-CN",
                                  {
                                    month: "2-digit",
                                    day: "2-digit",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  },
                                )}
                              </small>
                            )}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="watchlist-schedule">
            <label>
              <input
                type="checkbox"
                checked={data?.enabled ?? false}
                disabled={!data || disabled}
                onChange={(e) => onToggle(e.target.checked)}
              />
              每天自动更新
            </label>
            <p>{data?.schedule ?? "每天 18:00（北京时间）"}</p>
            <p>
              需本地服务运行；启动时补查。关闭网页后仍可更新，服务关闭期间暂停。
            </p>
          </div>
        </div>
      )}
    </aside>
  );
}
