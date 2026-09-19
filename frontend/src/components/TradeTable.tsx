import type { Trade } from "../types";
import { money, percent } from "../services/api";

export default function TradeTable({
  trades,
  selected,
  onSelect,
}: {
  trades: Trade[];
  selected: Trade | null;
  onSelect: (t: Trade) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {[
              "序号",
              "买入日期",
              "卖出日期",
              "买入价",
              "卖出价",
              "股数",
              "持仓天数",
              "净收益率",
              "MFE",
              "MAE",
              "盈亏 / 元",
            ].map((x) => (
              <th key={x}>{x}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr
              key={t.trade_id}
              className={selected?.trade_id === t.trade_id ? "selected" : ""}
              onClick={() => onSelect(t)}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(t);
                }
              }}
              aria-selected={selected?.trade_id === t.trade_id}
            >
              <td>
                <span className="trade-index">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </td>
              <td>{t.entry_date}</td>
              <td>{t.exit_date}</td>
              <td>{t.entry_price.toFixed(2)}</td>
              <td>{t.exit_price.toFixed(2)}</td>
              <td>{t.shares.toLocaleString()}</td>
              <td>{t.holding_days}</td>
              <td className={t.net_return >= 0 ? "positive" : "negative"}>
                {percent(t.net_return)}
              </td>
              <td className="muted">{percent(t.MFE)}</td>
              <td className="muted">{percent(t.MAE)}</td>
              <td className={t.profit >= 0 ? "positive" : "negative"}>
                {t.profit > 0 ? "+" : ""}
                {money(t.profit)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!trades.length && (
        <div className="table-empty">
          暂无完整买卖交易。运行回测后可在这里逐笔复盘；未平仓仓位单独列示。
        </div>
      )}
    </div>
  );
}
