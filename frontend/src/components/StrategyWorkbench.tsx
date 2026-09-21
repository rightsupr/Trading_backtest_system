import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Config, Query } from "../types";
import type {
  PythonExample,
  SavedStrategy,
  StrategyDefinition,
  StrategyVersion,
} from "../types/strategy";
import RuleEditor from "./RuleEditor";
import PythonEditor from "./PythonEditor";

interface Props {
  value: StrategyDefinition;
  onChange: (v: StrategyDefinition) => void;
  query: Query;
  config: Config;
  hasBars: boolean;
  disabled: boolean;
}
export default function StrategyWorkbench({
  value,
  onChange,
  query,
  config,
  hasBars,
  disabled,
}: Props) {
  const [examples, setExamples] = useState<PythonExample[]>([]);
  const [library, setLibrary] = useState<SavedStrategy[]>([]);
  const [parent, setParent] = useState<string | null>(null);
  const [localBusy, setLocalBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [preview, setPreview] = useState<
    { date: string; signal: string; reason: string }[]
  >([]);
  const [revision, setRevision] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SavedStrategy | null>(null);
  useEffect(() => {
    Promise.all([
      api<PythonExample[]>("/strategy-editor/examples"),
      api<SavedStrategy[]>("/strategy-editor/definitions"),
    ])
      .then(([e, s]) => {
        setExamples(e);
        setLibrary(s);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setMessage("");
    setPreview([]);
    setError("");
  }, [value, query]);
  const perform = async (action: () => Promise<void>) => {
    setLocalBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setLocalBusy(false);
    }
  };
  const save = (newFamily: boolean) =>
    perform(async () => {
      const result = await api<StrategyVersion>(
        "/strategy-editor/definitions",
        { definition: value, parent_id: newFamily ? null : parent },
      );
      setParent(result.definition_id);
      setRevision(result.revision);
      setSavedContent(JSON.stringify(value));
      setLibrary(await api<SavedStrategy[]>("/strategy-editor/definitions"));
      setMessage(
        `已保存 V${result.revision}。保存不会运行代码；运行回测会另存完整规则/代码快照。`,
      );
    });
  const load = (id: string) => {
    if (!id) return;
    void perform(async () => {
      const result = await api<StrategyVersion>(
        `/strategy-editor/definitions/${id}`,
      );
      onChange(result.definition);
      setParent(id);
      setRevision(result.revision);
      setSavedContent(JSON.stringify(result.definition));
    });
  };
  const validate = () =>
    perform(async () => {
      const result = await api<{
        message: string;
        rows: number;
        signal_counts: Record<string, number>;
        examples: typeof preview;
      }>("/strategy-editor/validate", {
        ...query,
        config,
        custom_strategy: value,
      });
      setMessage(
        `${result.message} · ${result.rows} 根 K 线 · BUY ${result.signal_counts.BUY ?? 0} / SELL ${result.signal_counts.SELL ?? 0}`,
      );
      setPreview(result.examples);
    });
  const modified = savedContent !== JSON.stringify(value);
  const current = library.find((s) => s.definition_id === parent);
  const remove = () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    void perform(async () => {
      await api(
        `/strategy-editor/definitions/${target.definition_id}/delete`,
        {},
      );
      setLibrary((items) =>
        items.filter((s) => s.definition_id !== target.definition_id),
      );
      setDeleteTarget(null);
      if (parent === target.definition_id) {
        setParent(null);
        setRevision(null);
        setSavedContent("");
      }
      setMessage(
        `已删除「${target.name} · V${target.revision}」。当前内容保留为草稿，历史回测不受影响。`,
      );
    });
  };
  return (
    <fieldset disabled={disabled || localBusy} className="strategy-workbench">
      <div className="workbench-header">
        <div>
          <strong>
            {value.name ||
              (value.kind === "rules" ? "规则策略" : "Python 策略")}
          </strong>
          <span>
            {revision
              ? `V${revision}${modified ? " · 已修改" : " · 已保存"}`
              : "未保存草稿"}{" "}
            · 草稿自动保存在此浏览器
          </span>
        </div>
        <div className="workbench-library-actions">
          <select
            aria-label="载入我的策略"
            value={parent ?? ""}
            onChange={(e) => load(e.target.value)}
          >
            <option value="">当前草稿 · 选择已保存策略</option>
            {library
              .filter((s) => s.kind === value.kind)
              .map((s) => (
                <option key={s.definition_id} value={s.definition_id}>
                  {s.name} · V{s.revision}
                </option>
              ))}
          </select>
          <button
            onClick={() => setEditing(!editing)}
            aria-expanded={editing}
            aria-controls="strategy-editing-content"
          >
            {editing ? "收起编辑器" : "编辑策略"}
          </button>
          <button
            disabled={!current}
            onClick={() => current && setDeleteTarget(current)}
            title="删除当前载入的策略版本"
          >
            删除版本
          </button>
        </div>
      </div>
      {!editing && (
        <p className="strategy-compact-description">
          {value.description ||
            "选择已保存策略后可直接运行回测，修改规则或代码请展开编辑。"}
        </p>
      )}
      {deleteTarget && (
        <div
          className="strategy-delete-confirm"
          role="alertdialog"
          aria-label="确认删除策略版本"
        >
          <strong>
            删除「{deleteTarget.name} · V{deleteTarget.revision}」？
          </strong>
          <p>
            该版本将从策略列表移除，其他版本和历史回测保留。当前编辑内容保留为草稿。
          </p>
          {modified && <p>当前有未保存的修改，删除后仍会保留在草稿中。</p>}
          <button onClick={() => setDeleteTarget(null)}>取消</button>
          <button onClick={remove}>确认删除此版本</button>
        </div>
      )}
      {editing && (
        <div id="strategy-editing-content">
          <div className="strategy-meta">
            <label>
              策略名称
              <input
                aria-label="自定义策略名称"
                maxLength={80}
                value={value.name}
                onChange={(e) => onChange({ ...value, name: e.target.value })}
              />
            </label>
            <label>
              策略说明
              <input
                aria-label="策略说明"
                maxLength={2000}
                placeholder="这个策略想捕捉什么走势？"
                value={value.description}
                onChange={(e) =>
                  onChange({ ...value, description: e.target.value })
                }
              />
            </label>
          </div>
          {value.kind === "rules" ? (
            <RuleEditor value={value} onChange={onChange} />
          ) : (
            <PythonEditor
              value={value}
              onChange={onChange}
              examples={examples}
            />
          )}
          <div className="workbench-actions">
            <button
              onClick={validate}
              disabled={!hasBars || localBusy || disabled}
            >
              校验策略与信号
            </button>
            <button onClick={() => save(false)} disabled={!value.name.trim()}>
              保存{parent ? "新版本" : "策略"}
            </button>
            {parent && <button onClick={() => save(true)}>另存为新策略</button>}
            <span>
              {localBusy
                ? "正在处理…"
                : hasBars
                  ? "校验使用当前本地行情，不创建回测记录。"
                  : "先下载或读取本地行情，即可校验与回测。"}
            </span>
          </div>
        </div>
      )}
      {(error || message) && (
        <p
          className={`editor-message ${error ? "editor-error" : ""}`}
          role={error ? "alert" : "status"}
        >
          {error || message}
        </p>
      )}
      {editing && !!preview.length && (
        <div className="signal-preview">
          <strong>前 5 个买卖信号（信号日）</strong>
          {preview.map((s, i) => (
            <p key={i}>
              <b>
                {s.date} · {s.signal}
              </b>{" "}
              {s.reason}
            </p>
          ))}
        </div>
      )}
    </fieldset>
  );
}
