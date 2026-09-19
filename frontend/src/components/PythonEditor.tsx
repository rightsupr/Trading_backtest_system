import type { PythonExample, StrategyDefinition } from "../types/strategy";

export default function PythonEditor({
  value,
  onChange,
  examples,
}: {
  value: StrategyDefinition;
  onChange: (v: StrategyDefinition) => void;
  examples: PythonExample[];
}) {
  const load = (example: PythonExample) =>
    onChange({
      ...value,
      name: example.name,
      description: example.description,
      code: example.code,
      parameters: example.parameters,
    });
  return (
    <div className="python-editor">
      <div className="python-examples">
        <span>从可运行的示例开始：</span>
        {examples.map((example) => (
          <button key={example.id} onClick={() => load(example)}>
            载入{example.name.replace("Python ", "")}示例
          </button>
        ))}
      </div>
      <div className="code-contract">
        <strong>固定入口：generate_signals(data, params)</strong>
        <p>
          输入为按日期递增的行情和指标 DataFrame；返回
          date、signal、position_target、reason
          四列。买卖成交、手续费和图表由系统处理。
        </p>
        <p>
          此入口执行本机
          Python，拥有当前用户的文件与网络权限，仅运行你信任的代码。独立进程与
          15 秒超时用于处理故障，不是安全沙箱。
        </p>
      </div>
      <label className="code-label">
        策略代码 · {value.code.split("\n").length} 行
        <textarea
          aria-label="Python 策略代码"
          className="code-editor"
          spellCheck={false}
          value={value.code}
          onChange={(e) => onChange({ ...value, code: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === "Tab") {
              e.preventDefault();
              const input = e.currentTarget;
              const start = input.selectionStart,
                end = input.selectionEnd;
              onChange({
                ...value,
                code:
                  value.code.slice(0, start) + "    " + value.code.slice(end),
              });
              requestAnimationFrame(() => {
                input.selectionStart = input.selectionEnd = start + 4;
              });
            }
          }}
        />
      </label>
      <div className="python-parameters">
        <strong>传入 params 的数值参数</strong>
        {Object.entries(value.parameters).map(([key, number]) => (
          <label key={key}>
            {key}
            <div>
              <input
                aria-label={`Python 参数 ${key}`}
                type="number"
                step="any"
                value={number}
                onChange={(e) =>
                  onChange({
                    ...value,
                    parameters: {
                      ...value.parameters,
                      [key]: Number(e.target.value),
                    },
                  })
                }
              />
              <button
                aria-label={`删除参数 ${key}`}
                className="text-button"
                onClick={() => {
                  const next = { ...value.parameters };
                  delete next[key];
                  onChange({ ...value, parameters: next });
                }}
              >
                ×
              </button>
            </div>
          </label>
        ))}
      </div>
      <label className="add-python-param">
        新增参数名称
        <input
          aria-label="新增 Python 参数"
          placeholder="例如 buy_threshold，回车添加"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              const key = e.currentTarget.value.trim();
              if (
                /^[A-Za-z_][A-Za-z0-9_]*$/.test(key) &&
                !(key in value.parameters)
              ) {
                onChange({
                  ...value,
                  parameters: { ...value.parameters, [key]: 0 },
                });
                e.currentTarget.value = "";
              }
            }
          }}
        />
      </label>
      <details className="python-reference">
        <summary>输入字段、返回格式和未来数据约束</summary>
        <p>
          输入：date、open/high/low/close、volume、amount、turnover，以及
          sma_5/sma_20、macd_dif/macd_dea/macd_hist、rsi、atr、boll_*、kdj_*、volume_ma、dif_slope、dea_slope。预热期可能为空。
        </p>
        <p>
          signal 使用 BUY/SELL/HOLD/NONE；position_target 使用 0 或 1；reason
          必須非空。target
          表示信号目标仓位，资金不足或停牌时可能与实际成交仓位不同。
        </p>
        <p>
          只能使用当日及更早数据。不要使用
          shift(-1)、居中滚动或全区间统计决定历史信号。系统抽查两处历史前缀的一致性，不能证明任意代码完全没有未来函数。
        </p>
        <p>
          示例可导入 app.indicators.technical 的 sma、ema、calculate_macd、slope
          等函数；自定义指标仅用于信号，图表目前仍显示标准指标。代码可用 Python
          和已安装依赖，无需继承类或修改系统目录。
        </p>
      </details>
    </div>
  );
}
