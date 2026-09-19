export async function api<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("无法连接本地服务，请确认后端已在 8000 端口启动");
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(
      Array.isArray(detail)
        ? detail.map((e: { msg: string }) => e.msg).join("；")
        : detail || `请求失败 (${response.status})`,
    );
  }
  return payload as T;
}
export const percent = (n: number | null | undefined) =>
  n == null ? "—" : `${n > 0 ? "+" : ""}${(n * 100).toFixed(2)}%`;
export const money = (n: number) =>
  n.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
