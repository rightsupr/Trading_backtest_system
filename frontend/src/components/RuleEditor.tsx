import type {
  Condition,
  Operand,
  RuleGroup,
  StrategyDefinition,
} from "../types/strategy";
import { operand } from "../types/strategy";

const features: Record<string, string> = {
  constant: "固定数值",
  close: "收盘价",
  open: "开盘价",
  high: "最高价",
  low: "最低价",
  volume: "成交量（股）",
  sma: "SMA 均线",
  ema: "EMA 均线",
  volume_ma: "成交量均线",
  macd_dif: "MACD DIF",
  macd_dea: "MACD DEA",
  macd_hist: "MACD 柱",
  rsi: "RSI (14)",
  atr: "ATR (14)",
  boll_upper: "BOLL 上轨 (20,2)",
  boll_mid: "BOLL 中轨 (20)",
  boll_lower: "BOLL 下轨 (20,2)",
  kdj_k: "KDJ K (9)",
  kdj_d: "KDJ D (9)",
  kdj_j: "KDJ J (9)",
};
const operators: Record<string, string> = {
  gt: "大于 >",
  gte: "大于等于 ≥",
  lt: "小于 <",
  lte: "小于等于 ≤",
  cross_up: "上穿 ↑",
  cross_down: "下穿 ↓",
};
const describeOperand = (o: Operand) =>
  o.feature === "constant"
    ? String(o.value)
    : `${features[o.feature]}${["sma", "ema", "volume_ma"].includes(o.feature) ? `(${o.period})` : ""}${o.slope_period ? `的 ${o.slope_period} 日斜率` : ""}${o.offset ? `（${o.offset} 根前）` : ""}`;
const describe = (c: Condition) =>
  `${describeOperand(c.left)} ${operators[c.operator]} ${describeOperand(c.right)}${c.consecutive > 1 ? `，连续 ${c.consecutive} 根成立` : ""}`;

function OperandInput({
  value,
  onChange,
  label,
}: {
  value: Operand;
  onChange: (v: Operand) => void;
  label: string;
}) {
  const update = (patch: Partial<Operand>) => onChange({ ...value, ...patch });
  return (
    <div className="operand-input">
      <select
        aria-label={`${label}指标`}
        value={value.feature}
        onChange={(e) =>
          update({ feature: e.target.value, slope_period: 0, offset: 0 })
        }
      >
        {Object.entries(features).map(([key, name]) => (
          <option key={key} value={key}>
            {name}
          </option>
        ))}
      </select>
      {value.feature === "constant" ? (
        <label>
          数值
          <input
            aria-label={`${label}数值`}
            type="number"
            step="any"
            value={value.value}
            onChange={(e) => update({ value: Number(e.target.value) })}
          />
        </label>
      ) : (
        <>
          {["sma", "ema", "volume_ma"].includes(value.feature) && (
            <label>
              周期
              <input
                aria-label={`${label}周期`}
                type="number"
                min={1}
                max={500}
                value={value.period}
                onChange={(e) => update({ period: Number(e.target.value) })}
              />
            </label>
          )}
          <label>
            斜率 N（0=原值）
            <input
              aria-label={`${label}斜率周期`}
              type="number"
              min={0}
              max={250}
              value={value.slope_period}
              onChange={(e) => update({ slope_period: Number(e.target.value) })}
            />
          </label>
          <label>
            前移几根
            <input
              aria-label={`${label}历史偏移`}
              type="number"
              min={0}
              max={250}
              value={value.offset}
              onChange={(e) => update({ offset: Number(e.target.value) })}
            />
          </label>
        </>
      )}
    </div>
  );
}

function GroupEditor({
  value,
  onChange,
  side,
}: {
  value: RuleGroup;
  onChange: (v: RuleGroup) => void;
  side: string;
}) {
  const update = (index: number, patch: Partial<Condition>) =>
    onChange({
      ...value,
      conditions: value.conditions.map((c, i) =>
        i === index ? { ...c, ...patch } : c,
      ),
    });
  return (
    <div className="rule-group">
      <div className="rule-group-header">
        <strong>{side}条件</strong>
        <select
          aria-label={`${side}条件组合`}
          value={value.match}
          onChange={(e) =>
            onChange({ ...value, match: e.target.value as RuleGroup["match"] })
          }
        >
          <option value="all">全部满足（AND）</option>
          <option value="any">任意满足（OR）</option>
        </select>
      </div>
      {value.conditions.map((condition, index) => (
        <div className="condition" key={index}>
          <div className="condition-heading">
            <span>
              {side}条件 {index + 1}
            </span>
            <button
              className="text-button"
              disabled={value.conditions.length === 1}
              onClick={() =>
                onChange({
                  ...value,
                  conditions: value.conditions.filter((_, i) => i !== index),
                })
              }
              aria-label={`删除${side}条件${index + 1}`}
            >
              删除
            </button>
          </div>
          <div className="condition-expression">
            <OperandInput
              label={`${side}${index + 1}左侧`}
              value={condition.left}
              onChange={(left) => update(index, { left })}
            />
            <select
              className="rule-operator"
              aria-label={`${side}${index + 1}比较方式`}
              value={condition.operator}
              onChange={(e) => update(index, { operator: e.target.value })}
            >
              {Object.entries(operators).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <OperandInput
              label={`${side}${index + 1}右侧`}
              value={condition.right}
              onChange={(right) => update(index, { right })}
            />
            <label className="consecutive-input">
              连续根数
              <input
                aria-label={`${side}${index + 1}连续根数`}
                type="number"
                min={1}
                max={250}
                value={condition.consecutive}
                onChange={(e) =>
                  update(index, { consecutive: Number(e.target.value) })
                }
              />
            </label>
          </div>
          <p className="rule-sentence">{describe(condition)}</p>
        </div>
      ))}
      <button
        className="text-button"
        disabled={value.conditions.length >= 20}
        onClick={() =>
          onChange({
            ...value,
            conditions: [
              ...value.conditions,
              {
                left: operand("macd_dif"),
                operator: "gt",
                right: operand("constant"),
                consecutive: 1,
              },
            ],
          })
        }
      >
        ＋ 添加{side}条件
      </button>
    </div>
  );
}

export default function RuleEditor({
  value,
  onChange,
}: {
  value: StrategyDefinition;
  onChange: (v: StrategyDefinition) => void;
}) {
  if (!value.rules) return null;
  return (
    <>
      <div className="rules-help">
        斜率 = (今天的值 − N 根前的值) / N；前移 1 根表示读取昨天。MACD 使用
        12/26/9；两组同时成立时卖出优先，空仓则不买入。持仓期间不重复买入。
      </div>
      <GroupEditor
        value={value.rules.buy}
        side="买入"
        onChange={(buy) =>
          onChange({ ...value, rules: { ...value.rules!, buy } })
        }
      />
      <GroupEditor
        value={value.rules.sell}
        side="卖出"
        onChange={(sell) =>
          onChange({ ...value, rules: { ...value.rules!, sell } })
        }
      />
      <p className="editor-footnote">
        本版支持一层 AND/OR
        和行情指标条件。实际持仓天数、持仓最高价止损与嵌套条件尚未纳入规则编辑器。信号基于当日及历史数据，默认按当日收盘价加减滑点撮合（尾盘近似）。
      </p>
    </>
  );
}
