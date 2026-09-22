import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Config, Query } from "../types";
import type {
  PythonExample,
  SavedStrategy,
  StrategyFile,
  StrategyDefinition,
  StrategyVersion,
} from "../types/strategy";
import PythonEditor from "./PythonEditor";

interface Props {
  value: StrategyDefinition;
  onChange: (v: StrategyDefinition) => void;
  fileName: string | null;
  onFileChange: (filename: string | null) => void;
  query: Query;
  config: Config;
  hasBars: boolean;
  disabled: boolean;
  deletedIds: string[];
}
export default function StrategyWorkbench({
  value,
  onChange,
  fileName,
  onFileChange,
  query,
  config,
  hasBars,
  disabled,
  deletedIds,
}: Props) {
  const [examples, setExamples] = useState<PythonExample[]>([]);
  const [library, setLibrary] = useState<SavedStrategy[]>([]);
  const [files, setFiles] = useState<StrategyFile[]>([]);
  const [fileDefinition, setFileDefinition] = useState<StrategyDefinition | null>(null);
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
  useEffect(() => {
    Promise.all([
      api<PythonExample[]>("/strategy-editor/examples"),
      api<SavedStrategy[]>("/strategy-editor/definitions"),
      api<StrategyFile[]>("/strategy-editor/files"),
    ])
      .then(([e, s, f]) => {
        setExamples(e);
        setLibrary(s);
        setFiles(f);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setLibrary((items) => items.filter((s) => !deletedIds.includes(s.definition_id)));
    if (parent && deletedIds.includes(parent)) {
      setParent(null);
      setRevision(null);
      setSavedContent("");
    }
  }, [deletedIds, parent]);
  useEffect(() => {
    if (!fileName) {
      setFileDefinition(null);
      return;
    }
    setFileDefinition(null);
    let cancelled = false;
    api<StrategyDefinition>(`/strategy-editor/files/${encodeURIComponent(fileName)}`)
      .then((definition) => {
        if (!cancelled) setFileDefinition(definition);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [fileName]);
  useEffect(() => {
    setMessage("");
    setPreview([]);
    setError("");
  }, [value, query, fileName]);
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
        `已保存 V${result.revision}。保存不会运行代码；运行回测会另存完整代码快照。`,
      );
    });
  const saveFile = () => {
    if (!fileName) return;
    void perform(async () => {
      const definition = await api<StrategyDefinition>(
        `/strategy-editor/files/${encodeURIComponent(fileName)}`,
      );
      const result = await api<StrategyVersion>(
        "/strategy-editor/definitions",
        { definition, parent_id: parent },
      );
      setFileDefinition(definition);
      setParent(result.definition_id);
      setRevision(result.revision);
      setSavedContent(JSON.stringify(definition));
      setLibrary(await api<SavedStrategy[]>("/strategy-editor/definitions"));
      setMessage(
        `已将 strategy/${fileName} 保存为 V${result.revision}。策略库保存的是本次代码副本；文件模式继续读取最新文件。`,
      );
    });
  };
  const load = (id: string) => {
    if (!id) return;
    if (library.find((item) => item.definition_id === id)?.kind === "rules") return;
    void perform(async () => {
      const result = await api<StrategyVersion>(
        `/strategy-editor/definitions/${id}`,
      );
      onChange(result.definition);
      onFileChange(null);
      setParent(id);
      setRevision(result.revision);
      setSavedContent(JSON.stringify(result.definition));
    });
  };
  const selectFile = (filename: string | null) => {
    setParent(null);
    setRevision(null);
    setSavedContent("");
    onFileChange(filename);
  };
  const refreshFiles = () =>
    perform(async () => {
      setFiles(await api<StrategyFile[]>("/strategy-editor/files"));
      if (fileName) {
        setFileDefinition(await api<StrategyDefinition>(
          `/strategy-editor/files/${encodeURIComponent(fileName)}`,
        ));
      }
      setMessage("已读取 strategy 文件夹中的最新策略和代码。校验与回测也会重新读取文件。");
    });
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
        custom_strategy: fileName ? null : value,
        strategy_file: fileName,
      });
      setMessage(
        `${result.message} · ${result.rows} 根 K 线 · BUY ${result.signal_counts.BUY ?? 0} / SELL ${result.signal_counts.SELL ?? 0}`,
      );
      setPreview(result.examples);
    });
  const modified = savedContent !== JSON.stringify(value);
  const activeValue = fileName && fileDefinition ? fileDefinition : value;
  return (
    <fieldset disabled={disabled || localBusy} className="strategy-workbench">
      <div className="workbench-header">
        <div>
          <strong>
            {fileName ? fileDefinition?.name ?? fileName : value.name || "Python 策略"}
          </strong>
          <span>
            {fileName ? `文件策略 · strategy/${fileName}${revision ? ` · 已存 V${revision}` : ""}` : revision
              ? `V${revision}${modified ? " · 已修改" : " · 已保存"}`
              : "未保存草稿"}{" "}
            {fileName ? " · 运行时读取最新文件" : " · 草稿自动保存在此浏览器"}
          </span>
        </div>
        <div className="workbench-library-actions">
          <select
            aria-label="载入我的策略"
            value={fileName ? "" : parent ?? ""}
            onChange={(e) => load(e.target.value)}
          >
            <option value="" disabled>选择已保存策略</option>
            {library.filter((s) => s.kind === "python").map((s) => (
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
            {editing ? "收起编辑器" : fileName ? "查看文件代码" : "编辑策略"}
          </button>
        </div>
      </div>
      {value.kind === "python" && (
        <div className="strategy-file-picker">
          <label>
            VS Code 文件策略
            <select
              aria-label="选择 strategy 文件夹中的策略"
              value={fileName ?? ""}
              onChange={(e) => selectFile(e.target.value || null)}
            >
              <option value="">在线编辑器草稿</option>
              {files.map((file) => (
                <option key={file.filename} value={file.filename}>
                  {file.filename}
                </option>
              ))}
            </select>
          </label>
          <button onClick={refreshFiles}>刷新文件列表与预览</button>
          {fileName && (
            <button onClick={saveFile} disabled={!fileDefinition}>
              {parent ? "保存文件新版本" : "保存文件到策略库"}
            </button>
          )}
          <span>放入项目的 strategy 文件夹；校验和回测每次读取最新文件。</span>
        </div>
      )}
      {!editing && (
        <p className="strategy-compact-description">
          {activeValue.description ||
            "选择已保存策略后可直接运行回测，修改代码请展开编辑。"}
        </p>
      )}
      {editing && fileName && (
        <div id="strategy-editing-content" className="strategy-file-preview">
          <p>在 VS Code 修改 strategy/{fileName}。此处显示上次读取的代码；点击“刷新文件列表与预览”查看最新内容。</p>
          <pre className="code-editor">{fileDefinition?.code ?? "正在读取文件…"}</pre>
          <div className="workbench-actions">
            <button onClick={validate} disabled={!hasBars}>校验策略与信号</button>
            <span>{hasBars ? "校验时读取最新文件。" : "先下载或读取本地行情。"}</span>
          </div>
        </div>
      )}
      {editing && !fileName && (
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
          <PythonEditor
            value={value}
            onChange={onChange}
            examples={examples}
          />
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
