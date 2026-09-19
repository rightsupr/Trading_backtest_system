export type StrategyMode = "builtin" | "rules" | "python";
export interface Operand {
  feature: string;
  value: number;
  period: number;
  slope_period: number;
  offset: number;
}
export interface Condition {
  left: Operand;
  operator: string;
  right: Operand;
  consecutive: number;
}
export interface RuleGroup {
  match: "all" | "any";
  conditions: Condition[];
}
export interface StrategyDefinition {
  kind: "rules" | "python";
  name: string;
  description: string;
  rules: { buy: RuleGroup; sell: RuleGroup } | null;
  code: string;
  parameters: Record<string, number>;
}
export interface SavedStrategy {
  definition_id: string;
  family_id: string;
  revision: number;
  name: string;
  kind: "rules" | "python";
  created_at: string;
}
export interface StrategyVersion {
  definition_id: string;
  revision: number;
  definition: StrategyDefinition;
}
export interface PythonExample {
  id: string;
  name: string;
  description: string;
  code: string;
  parameters: Record<string, number>;
}

export const operand = (
  feature = "close",
  period = 20,
  value = 0,
): Operand => ({ feature, period, value, slope_period: 0, offset: 0 });
export const defaultRules: StrategyDefinition = {
  kind: "rules",
  name: "我的均线策略",
  description: "短均线上穿长均线买入，下穿卖出。",
  code: "",
  parameters: {},
  rules: {
    buy: {
      match: "all",
      conditions: [
        {
          left: operand("sma", 5),
          operator: "cross_up",
          right: operand("sma", 20),
          consecutive: 1,
        },
      ],
    },
    sell: {
      match: "any",
      conditions: [
        {
          left: operand("sma", 5),
          operator: "cross_down",
          right: operand("sma", 20),
          consecutive: 1,
        },
      ],
    },
  },
};
export const defaultPython: StrategyDefinition = {
  kind: "python",
  name: "我的 Python 策略",
  description: "",
  code: "",
  rules: null,
  parameters: {},
};

export function readDraft(
  key: string,
  fallback: StrategyDefinition,
): StrategyDefinition {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) ?? "null");
    return parsed &&
      parsed.kind === fallback.kind &&
      typeof parsed.code === "string" &&
      typeof parsed.name === "string" &&
      parsed.parameters &&
      (fallback.kind !== "rules" ||
        (parsed.rules?.buy?.conditions?.length &&
          parsed.rules?.sell?.conditions?.length))
      ? parsed
      : structuredClone(fallback);
  } catch {
    return structuredClone(fallback);
  }
}
