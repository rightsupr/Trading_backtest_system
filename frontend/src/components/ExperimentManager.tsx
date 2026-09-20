import { useEffect, useRef, useState } from "react";
import { Database, Star, Trash2, X } from "lucide-react";
import { api } from "../services/api";

interface Experiment {
  run_id: string;
  symbol: string;
  strategy_name: string;
  label: string;
  created_at: string;
  start_date: string;
  end_date: string;
  is_favorite: boolean;
  snapshot_bytes: number;
}
interface HistoryPage {
  items: Experiment[];
  total: number;
  page: number;
  page_size: number;
  storage: {
    database_bytes: number;
    wal_bytes: number;
    total_bytes: number;
    snapshot_bytes: number;
    run_count: number;
    favorite_count: number;
    bar_count: number;
  };
}
interface DeleteResult {
  deleted_ids: string[];
  protected_ids: string[];
  missing_ids: string[];
}
const bytes = (n: number) =>
  n < 1024
    ? `${n} B`
    : n < 1024 ** 2
      ? `${(n / 1024).toFixed(1)} KiB`
      : `${(n / 1024 ** 2).toFixed(2)} MiB`;
const label = (r: Experiment) =>
  r.label === "ma_cross"
    ? "双均线交叉"
    : r.label === "macd"
      ? "MACD 交叉"
      : r.label;

export default function ExperimentManager({
  onClose,
  onOpen,
  onDeleted,
}: {
  onClose: () => void;
  onOpen: (id: string) => void;
  onDeleted: (ids: string[]) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<HistoryPage | null>(null);
  const [page, setPage] = useState(1);
  const [favorites, setFavorites] = useState(false);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirm, setConfirm] = useState<Experiment[] | null>(null);
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
    api<HistoryPage>(`/experiments?page=${page}&favorites=${favorites}`)
      .then((result) => {
        if (active) {
          setData(result);
          setPage(result.page);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [page, favorites, revision]);
  const eligible = data?.items.filter((r) => !r.is_favorite) ?? [];
  const toggleFavorite = async (r: Experiment) => {
    setBusy(true);
    setError("");
    try {
      await api(`/experiments/${r.run_id}/favorite`, {
        is_favorite: !r.is_favorite,
      });
      setNotice(
        r.is_favorite ? "已取消收藏" : "已收藏，删除时会自动保护这条实验",
      );
      setRevision((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "收藏操作失败");
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<DeleteResult>("/experiments/delete", {
        run_ids: confirm.map((r) => r.run_id),
      });
      setConfirm(null);
      setNotice(
        `已删除 ${result.deleted_ids.length} 条实验` +
          (result.protected_ids.length
            ? `，跳过 ${result.protected_ids.length} 条已收藏实验`
            : "") +
          (result.missing_ids.length
            ? `，${result.missing_ids.length} 条已不存在`
            : ""),
      );
      onDeleted(result.deleted_ids);
      setRevision((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <dialog
      ref={dialog}
      className="experiment-dialog"
      aria-labelledby="experiment-title"
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
          <div className="eyebrow">EXPERIMENT LIBRARY</div>
          <h2 id="experiment-title">实验记录管理</h2>
          <p>保留重要结果，清理探索过程中的重复实验。</p>
        </div>
        <button
          autoFocus
          aria-label="关闭实验记录管理"
          disabled={busy}
          onClick={() => dialog.current?.close()}
        >
          <X size={18} />
        </button>
      </header>
      {data && (
        <>
          <div className="storage-grid">
            <div>
              <span>
                <Database size={15} /> 数据库实际占用
              </span>
              <strong>{bytes(data.storage.total_bytes)}</strong>
              <small>
                数据库 {bytes(data.storage.database_bytes)} · 日志{" "}
                {bytes(data.storage.wal_bytes)}
              </small>
            </div>
            <div>
              <span>实验快照总大小</span>
              <strong>{bytes(data.storage.snapshot_bytes)}</strong>
              <small>未压缩 JSON，非独立文件占用</small>
            </div>
            <div>
              <span>已保存实验</span>
              <strong>
                {data.storage.run_count} <em>条</em>
              </strong>
              <small>其中 {data.storage.favorite_count} 条已收藏</small>
            </div>
          </div>
          <p className="storage-note">
            实际占用包含共享行情、策略与实验数据；当前有{" "}
            {data.storage.bar_count.toLocaleString()}{" "}
            条行情。删除后数据库文件可能不会立即缩小，空闲空间可供后续写入复用。
          </p>
        </>
      )}
      {notice && (
        <p role="status" className="experiment-notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="experiment-error">
          {error}{" "}
          <button disabled={blocked} onClick={() => setRevision((v) => v + 1)}>
            重试加载
          </button>
        </p>
      )}
      {confirm ? (
        <section className="delete-confirm" aria-labelledby="delete-title">
          <h3 id="delete-title">确认删除 {confirm.length} 条实验？</h3>
          <p>
            将永久删除以下实验的回测快照、信号、交易明细与资金曲线，无法撤销。共享行情和已保存策略会保留；已收藏实验会自动跳过。
          </p>
          <ul>
            {confirm.map((r) => (
              <li key={r.run_id}>
                {r.symbol} · {label(r)} · {r.created_at.slice(0, 19)}{" "}
                <small>#{r.run_id.slice(0, 8)}</small>
              </li>
            ))}
          </ul>
          <div className="experiment-actions">
            <button
              disabled={busy}
              onClick={() => {
                setConfirm(null);
                setError("");
              }}
            >
              取消
            </button>
            <button
              className="danger-button"
              disabled={busy}
              onClick={() => void remove()}
            >
              {busy ? "正在删除…" : "确认永久删除"}
            </button>
          </div>
        </section>
      ) : (
        <>
          <div className="experiment-toolbar">
            <label>
              <input
                type="checkbox"
                checked={favorites}
                disabled={blocked}
                onChange={(e) => {
                  setFavorites(e.target.checked);
                  setPage(1);
                }}
              />
              <Star size={15} /> 只看收藏
            </label>
            <span>已选 {selected.length} 条 · 收藏实验不参与删除</span>
            <button
              className="danger-button"
              disabled={blocked || !selected.length}
              onClick={() =>
                setConfirm(
                  data!.items.filter((r) => selected.includes(r.run_id)),
                )
              }
            >
              <Trash2 size={15} />
              删除所选
            </button>
            <button
              disabled={blocked}
              onClick={() => setRevision((v) => v + 1)}
            >
              刷新
            </button>
          </div>
          <div className="experiment-table-wrap" aria-busy={loading}>
            <table className="experiment-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="选择本页未收藏实验"
                      disabled={blocked || !eligible.length}
                      checked={
                        !!eligible.length && selected.length === eligible.length
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked ? eligible.map((r) => r.run_id) : [],
                        )
                      }
                    />
                  </th>
                  <th>收藏</th>
                  <th>实验 / 股票</th>
                  <th>回测区间</th>
                  <th>创建时间</th>
                  <th>
                    快照大小<small>未压缩</small>
                  </th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((r) => (
                  <tr key={r.run_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`选择实验 ${r.run_id}`}
                        disabled={blocked || r.is_favorite}
                        checked={selected.includes(r.run_id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, r.run_id]
                              : selected.filter((id) => id !== r.run_id),
                          )
                        }
                      />
                    </td>
                    <td>
                      <button
                        className={
                          r.is_favorite
                            ? "favorite-button active"
                            : "favorite-button"
                        }
                        aria-label={`${r.is_favorite ? "取消收藏" : "收藏实验"} ${r.run_id}`}
                        aria-pressed={r.is_favorite}
                        disabled={blocked}
                        onClick={() => void toggleFavorite(r)}
                      >
                        <Star
                          size={17}
                          fill={r.is_favorite ? "currentColor" : "none"}
                        />
                      </button>
                    </td>
                    <td>
                      <strong>{label(r)}</strong>
                      <small>
                        {r.symbol} · #{r.run_id.slice(0, 8)}
                      </small>
                    </td>
                    <td>
                      {r.start_date}
                      <small>至 {r.end_date}</small>
                    </td>
                    <td>
                      {r.created_at.slice(0, 10)}
                      <small>{r.created_at.slice(11, 19)}</small>
                    </td>
                    <td>{bytes(r.snapshot_bytes)}</td>
                    <td>
                      <div className="experiment-actions">
                        <button
                          disabled={blocked}
                          onClick={() => onOpen(r.run_id)}
                        >
                          查看
                        </button>
                        <button
                          aria-label={`删除实验 ${r.run_id}`}
                          title={
                            r.is_favorite ? "请先取消收藏" : "删除这条实验"
                          }
                          disabled={blocked || r.is_favorite}
                          onClick={() => setConfirm([r])}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading ? (
              <p className="experiment-empty" role="status">
                正在读取实验记录…
              </p>
            ) : (
              !data?.items.length &&
              !error && (
                <p className="experiment-empty">
                  {favorites
                    ? "暂无收藏，点击实验旁的星标即可收藏。"
                    : "暂无实验记录，运行一次回测后会自动保存在这里。"}
                </p>
              )
            )}
          </div>
          <footer className="experiment-pagination">
            <span>
              共 {data?.total ?? 0} 条 · 第 {data?.page ?? 1} /{" "}
              {Math.max(1, Math.ceil((data?.total ?? 0) / 20))} 页
            </span>
            <button
              disabled={blocked || page <= 1}
              onClick={() => setPage(page - 1)}
            >
              上一页
            </button>
            <button
              disabled={
                blocked || !data || data.page * data.page_size >= data.total
              }
              onClick={() => setPage(page + 1)}
            >
              下一页
            </button>
          </footer>
        </>
      )}
    </dialog>
  );
}
