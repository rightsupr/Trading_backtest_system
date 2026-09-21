import { useState } from "react";
import type {
  ChartPreferences,
  Plot,
  PlotPreference,
} from "../charts/indicatorCatalog";
import { emptyPreferences } from "../charts/indicatorCatalog";

export default function ChartSettings({
  plots,
  preferences,
  onChange,
}: {
  plots: Plot[];
  preferences: ChartPreferences;
  onChange: (p: ChartPreferences) => void;
}) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"MA" | "EMA">("MA");
  const [period, setPeriod] = useState("60");
  const [error, setError] = useState("");
  const update = (key: string, patch: Partial<PlotPreference>) =>
    onChange({
      ...preferences,
      overrides: {
        ...preferences.overrides,
        [key]: { ...preferences.overrides[key], ...patch },
      },
    });
  const add = () => {
    const number = Number(period);
    if (!Number.isInteger(number) || number < 1 || number > 500) {
      setError("周期请输入 1–500 的整数");
      return;
    }
    if (
      preferences.averages.some((a) => a.kind === kind && a.period === number)
    ) {
      setError("该周期已添加");
      return;
    }
    if (preferences.averages.length >= 20) {
      setError("最多添加 20 条自定义均线");
      return;
    }
    onChange({
      ...preferences,
      averages: [...preferences.averages, { kind, period: number }],
    });
    setError("");
  };
  return (
    <div className="chart-settings">
      <div className="chart-settings-toolbar">
        <button onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "收起图表设置" : "图表设置"}
        </button>
        <span>
          {plots.filter((p) => p.line).length} 个图形 ·{" "}
          {plots.filter((p) => p.value).length} 个悬停数值
        </span>
      </div>
      {open && (
        <div className="chart-settings-body">
          <p>
            主图叠加价格指标，副图使用独立刻度。曲线和左上角数值可分别选择；预热期或缺失数据显示
            —。设置保存在此浏览器，不改变策略和回测结果。
          </p>
          <div className="chart-average-add">
            <label>
              均线类型
              <select
                aria-label="均线类型"
                value={kind}
                onChange={(e) => setKind(e.target.value as "MA" | "EMA")}
              >
                <option>MA</option>
                <option>EMA</option>
              </select>
            </label>
            <label>
              周期
              <input
                aria-label="均线周期"
                type="number"
                min="1"
                max="500"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              />
            </label>
            <button onClick={add}>添加均线</button>
            <button onClick={() => onChange(emptyPreferences())}>
              恢复默认图表
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
          <div className="chart-settings-table">
            <table>
              <thead>
                <tr>
                  <th>指标 / 数据</th>
                  <th>画线 / 柱</th>
                  <th>悬停数值</th>
                  <th>位置</th>
                  <th>颜色</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {plots.map((p) => (
                  <tr key={p.key}>
                    <td>
                      {p.label}
                      {p.key.startsWith("python:") && (
                        <small> · 策略输出</small>
                      )}
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`绘制 ${p.label}`}
                        checked={p.line}
                        onChange={(e) =>
                          update(p.key, { line: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`数值 ${p.label}`}
                        checked={p.value}
                        onChange={(e) =>
                          update(p.key, { value: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <select
                        aria-label={`位置 ${p.label}`}
                        value={p.pane}
                        onChange={(e) =>
                          update(p.key, { pane: e.target.value })
                        }
                      >
                        {[
                          ...new Set([
                            "price",
                            p.pane,
                            p.label,
                            "成交量",
                            "MACD",
                          ]),
                        ].map((pane) => (
                          <option key={pane} value={pane}>
                            {pane === "price" ? "K 线主图" : `${pane}副图`}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        aria-label={`颜色 ${p.label}`}
                        type="color"
                        value={p.color}
                        onChange={(e) =>
                          update(p.key, { color: e.target.value })
                        }
                      />
                    </td>
                    <td>
                      {p.key.startsWith("custom:") && (
                        <button
                          aria-label={`移除 ${p.label}`}
                          onClick={() => {
                            const [, k, n] = p.key.split(":");
                            const overrides = { ...preferences.overrides };
                            delete overrides[p.key];
                            onChange({
                              overrides,
                              averages: preferences.averages.filter(
                                (a) =>
                                  !(a.kind === k && a.period === Number(n)),
                              ),
                            });
                          }}
                        >
                          移除
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Python 策略返回 plot_
            开头的数值列，会在回测后自动绘制；更详细的位置、名称和颜色声明见
            Python 编辑器的绘图说明。
          </p>
        </div>
      )}
    </div>
  );
}
