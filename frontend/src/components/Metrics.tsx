import { percent } from "../services/api";
import type { Run } from "../types";

export default function Metrics({ run }: { run: Run | null }) {
  const values = [
    ["总收益率", "total_return", true],
    ["年化收益率", "annualized_return", true],
    ["最大回撤", "max_drawdown", true],
    ["胜率", "win_rate", true],
    ["完整交易", "number_of_trades", false],
    ["盈亏比", "profit_loss_ratio", false],
    ["平均持仓 / 天", "average_holding_days", false],
  ] as const;
  return (
    <div className="metrics">
      {values.map(([label, key, isPercent]) => {
        const value = run?.metrics[key];
        return (
          <div className="metric" key={key}>
            <span>{label}</span>
            <strong
              className={
                value != null &&
                ["total_return", "annualized_return", "max_drawdown"].includes(
                  key,
                )
                  ? value >= 0
                    ? "positive"
                    : "negative"
                  : ""
              }
            >
              {value == null
                ? "—"
                : isPercent
                  ? percent(value)
                  : key === "number_of_trades"
                    ? value
                    : value.toFixed(2)}
            </strong>
            <small>
              {key === "total_return"
                ? "包含期末持仓市值"
                : key === "annualized_return"
                  ? "252 交易日口径"
                  : key === "max_drawdown"
                    ? "每日收盘权益"
                    : key === "win_rate"
                      ? "已平仓交易口径"
                      : key === "profit_loss_ratio"
                        ? "平均盈利 / 平均亏损"
                        : key === "number_of_trades"
                          ? "不包含未平仓仓位"
                          : "自然日口径"}
            </small>
          </div>
        );
      })}
    </div>
  );
}
