import { useEffect, useRef, useState } from "react";
import { Trash2, X } from "lucide-react";
import { api } from "../services/api";
import type { SavedStrategy } from "../types/strategy";

interface DeleteResult {
  deleted_ids: string[];
  missing_ids: string[];
}

export default function StrategyManager({
  onClose,
  onDeleted,
}: {
  onClose: () => void;
  onDeleted: (ids: string[]) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const selectAll = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<SavedStrategy[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirm, setConfirm] = useState<SavedStrategy[] | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const blocked = loading || busy;

  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setSelected([]);
    api<SavedStrategy[]>("/strategy-editor/definitions")
      .then((result) => {
        if (active) setItems(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    if (selectAll.current) {
      selectAll.current.indeterminate = selected.length > 0 && selected.length < items.length;
    }
  }, [selected, items, confirm]);

  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<DeleteResult>("/strategy-editor/definitions/delete", {
        definition_ids: confirm.map((item) => item.definition_id),
      });
      const removed = [...result.deleted_ids, ...result.missing_ids];
      setItems((values) => values.filter((item) => !removed.includes(item.definition_id)));
      setSelected([]);
      setConfirm(null);
      setNotice(
        `已删除 ${result.deleted_ids.length} 个策略版本。` +
        (result.missing_ids.length ? `${result.missing_ids.length} 个版本已不存在。` : ""),
      );
      onDeleted(removed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败，请重试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={dialog}
      className="experiment-dialog strategy-manager"
      aria-labelledby="strategy-manager-title"
      onClose={onClose}
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else if (confirm) {
          e.preventDefault();
          setConfirm(null);
        }
      }}
    >
      <header className="experiment-header">
        <div>
          <div className="eyebrow">STRATEGY LIBRARY</div>
          <h2 id="strategy-manager-title">策略管理</h2>
          <p>管理网页编辑和 Python 文件保存的策略版本，勾选后可批量删除。</p>
        </div>
        <button
          autoFocus
          aria-label="关闭策略管理"
          disabled={busy}
          onClick={() => dialog.current?.close()}
        >
          <X size={18} />
        </button>
      </header>
      {notice && <p className="experiment-notice" role="status">{notice}</p>}
      {error && <p className="experiment-error" role="alert">{error}</p>}
      {confirm ? (
        <section className="delete-confirm" aria-labelledby="strategy-delete-title">
          <h3 id="strategy-delete-title">确认删除 {confirm.length} 个策略版本？</h3>
          <p>这些版本将从已保存策略中移除。历史回测、当前编辑内容和 strategy 文件夹中的源文件保留。</p>
          <ul>
            {confirm.map((item) => (
              <li key={item.definition_id}>{item.name} · V{item.revision}</li>
            ))}
          </ul>
          <div className="experiment-actions">
            <button disabled={busy} onClick={() => { setConfirm(null); setError(""); }}>取消</button>
            <button className="danger-button" disabled={busy} onClick={() => void remove()}>
              {busy ? "正在删除…" : "确认删除所选策略"}
            </button>
          </div>
        </section>
      ) : (
        <>
          <div className="experiment-toolbar">
            <span>共 {items.length} 个版本 · 已选 {selected.length} 个</span>
            <button
              className="danger-button"
              disabled={blocked || !selected.length}
              onClick={() => {
                setNotice("");
                setConfirm(items.filter((item) => selected.includes(item.definition_id)));
              }}
            >
              <Trash2 size={15} /> 删除所选
            </button>
            <button disabled={blocked} onClick={() => setRefresh((value) => value + 1)}>刷新</button>
          </div>
          <div className="experiment-table-wrap" aria-busy={loading}>
            <table className="experiment-table">
              <thead>
                <tr>
                  <th>
                    <input
                      ref={selectAll}
                      type="checkbox"
                      aria-label="全选已保存策略"
                      disabled={blocked || !items.length}
                      checked={!!items.length && selected.length === items.length}
                      onChange={(e) => setSelected(e.target.checked ? items.map((item) => item.definition_id) : [])}
                    />
                  </th>
                  <th>策略名称</th>
                  <th>版本</th>
                  <th>类型</th>
                  <th>保存时间</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.definition_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`选择策略 ${item.name} V${item.revision}`}
                        disabled={blocked}
                        checked={selected.includes(item.definition_id)}
                        onChange={(e) => setSelected((ids) => e.target.checked
                          ? [...ids, item.definition_id]
                          : ids.filter((id) => id !== item.definition_id))}
                      />
                    </td>
                    <td><strong>{item.name}</strong></td>
                    <td>V{item.revision}</td>
                    <td>{item.kind === "python" ? "Python" : "旧规则"}</td>
                    <td>{item.created_at.slice(0, 10)}<small>{item.created_at.slice(11, 19)}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading ? (
              <p className="experiment-empty" role="status">正在读取已保存策略…</p>
            ) : !items.length && !error ? (
              <p className="experiment-empty">暂无已保存策略。在 Python 编辑器或文件策略区域保存后，会显示在这里。</p>
            ) : null}
          </div>
        </>
      )}
    </dialog>
  );
}
