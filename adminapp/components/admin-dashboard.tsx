"use client";

import { startTransition, useEffect, useEffectEvent, useState } from "react";
import { useRouter } from "next/navigation";

type AdminEvent = {
  id: number;
  level: string;
  category: string;
  event_type: string;
  actor_type: string;
  actor_id: string;
  username: string;
  mac: string;
  message: string;
  raw_message?: string;
  display_username?: string;
  display_mac?: string;
  is_no_device_preview?: boolean;
  usage_source?: string;
  api_kind?: string;
  model_name?: string;
  details: Record<string, unknown>;
  created_at: string;
};

type InviteCode = {
  id?: number;
  code: string;
  is_used?: boolean;
  generated_at: string;
  used_at?: string;
  used_by_username?: string;
  grant_amount: number;
  remark: string;
  batch_id: string;
  generated_by?: string;
};

type UserSummary = {
  id: number;
  username: string;
  role: string;
  created_at: string;
  free_quota_remaining: number;
  total_calls_made: number;
  device_count: number;
};

type DeviceSummary = {
  mac: string;
  last_persona: string;
  last_refresh_at: string;
  updated_at: string;
  total_renders: number;
  owner_username: string;
};

type OverviewResponse = {
  viewer: { username: string };
  overview: {
    total_users: number;
    total_llm_calls: number;
    total_invite_codes: number;
    used_invite_codes: number;
    unused_invite_codes: number;
    total_devices: number;
    total_renders: number;
    recent_error_count: number;
  };
  recent_errors: AdminEvent[];
  recent_admin_actions: AdminEvent[];
};

export function AdminDashboard() {
  const AUTO_REFRESH_MS = 12000;
  const router = useRouter();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [invites, setInvites] = useState<InviteCode[]>([]);
  const [logs, setLogs] = useState<AdminEvent[]>([]);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [inviteCount, setInviteCount] = useState("10");
  const [grantAmount, setGrantAmount] = useState("50");
  const [remark, setRemark] = useState("");
  const [prefix, setPrefix] = useState("INK");
  const [inviteSubmitting, setInviteSubmitting] = useState(false);
  const [inviteMessage, setInviteMessage] = useState("");
  const [logCategory, setLogCategory] = useState("");
  const [logLevel, setLogLevel] = useState("");
  const [logQuery, setLogQuery] = useState("");

  async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
    const res = await fetch(url, { cache: "no-store", ...init });
    if (res.status === 401) {
      router.replace("/login");
      throw new Error("unauthorized");
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(typeof body.error === "string" ? body.error : "request failed");
    }
    return body as T;
  }

  async function loadAll(
    logOverrides?: { category?: string; level?: string; q?: string },
    options?: { silent?: boolean },
  ) {
    const silent = Boolean(options?.silent && overview);
    if (silent) {
      setIsRefreshing(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const search = new URLSearchParams();
      const category = logOverrides?.category ?? logCategory;
      const level = logOverrides?.level ?? logLevel;
      const q = logOverrides?.q ?? logQuery;
      if (category) search.set("category", category);
      if (level) search.set("level", level);
      if (q) search.set("q", q);

      const [overviewRes, inviteRes, logRes, userRes, deviceRes] = await Promise.all([
        fetchJson<OverviewResponse>("/api/admin/overview"),
        fetchJson<{ items: InviteCode[] }>("/api/admin/invite-codes?status=all&limit=20"),
        fetchJson<{ items: AdminEvent[] }>(`/api/admin/logs?limit=20&${search.toString()}`),
        fetchJson<{ items: UserSummary[] }>("/api/admin/users?limit=10"),
        fetchJson<{ items: DeviceSummary[] }>("/api/admin/devices?limit=10"),
      ]);
      setOverview(overviewRes);
      setInvites(inviteRes.items);
      setLogs(logRes.items);
      setUsers(userRes.items);
      setDevices(deviceRes.items);
      setLastUpdatedAt(new Date().toISOString());
    } catch (err) {
      if (err instanceof Error && err.message === "unauthorized") return;
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pollLatest = useEffectEvent(() => {
    if (typeof document !== "undefined" && document.visibilityState !== "visible") {
      return;
    }
    startTransition(() => {
      void loadAll(undefined, { silent: true });
    });
  });

  useEffect(() => {
    const timer = window.setInterval(() => {
      pollLatest();
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  async function handleGenerateInvites() {
    setInviteSubmitting(true);
    setInviteMessage("");
    try {
      const res = await fetchJson<{ ok: boolean; batch_id: string; items: InviteCode[] }>("/api/admin/invite-codes/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          count: Number(inviteCount),
          grant_amount: Number(grantAmount),
          remark,
          prefix,
        }),
      });
      setInviteMessage(`已生成 ${res.items.length} 个邀请码，批次 ${res.batch_id}`);
      startTransition(() => {
        void loadAll();
      });
    } catch (err) {
      setInviteMessage(err instanceof Error ? err.message : "生成失败");
    } finally {
      setInviteSubmitting(false);
    }
  }

  async function handleLogout() {
    await fetch("/api/admin/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  const visibleLogUsers = Array.from(
    new Set(logs.map((item) => item.display_username || item.username || "anonymous")),
  );
  const noDevicePreviewCount = logs.filter((item) => item.is_no_device_preview || item.display_mac === "no device preview").length;
  const lastUpdatedLabel = lastUpdatedAt
    ? new Date(lastUpdatedAt).toLocaleTimeString("zh-CN", { hour12: false })
    : "--:--:--";

  if (loading && !overview) {
    return (
      <div className="admin-shell">
        <div className="empty-state">正在加载管理员面板...</div>
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <div className="topbar">
        <div className="topbar-card" style={{ flex: 1 }}>
          <p className="eyebrow">InkSight Operations Console</p>
          <h1>运营与排障后台</h1>
          <p>
            一个独立的管理台，用于邀请码发放、基础指标观察、应用日志检索，以及对用户/设备状态做快速判断。
          </p>
        </div>
        <div className="stack" style={{ minWidth: 280 }}>
          <div className="viewer-chip">
            <span className="muted">当前管理员</span>
            <strong>{overview?.viewer.username || "admin"}</strong>
          </div>
          <div className={`live-chip ${isRefreshing ? "syncing" : ""}`}>
            <span className="live-dot" />
            <strong>Live</strong>
            <span className="muted">
              {isRefreshing ? "同步中..." : `每 ${Math.floor(AUTO_REFRESH_MS / 1000)} 秒刷新，最近一次 ${lastUpdatedLabel}`}
            </span>
          </div>
          <button className="button secondary" onClick={handleLogout}>退出登录</button>
        </div>
      </div>

      {error ? <div className="error-text" style={{ marginBottom: 14 }}>{error}</div> : null}

      <div className="dashboard-layout">
        <aside className="sidebar">
          <p className="sidebar-section-title">Modules</p>
          <div className="nav-list">
            <div className="nav-item">总览看板</div>
            <div className="nav-item">邀请码批量生成</div>
            <div className="nav-item">邀请码状态查询</div>
            <div className="nav-item">应用日志检索</div>
            <div className="nav-item">用户额度概览</div>
            <div className="nav-item">设备运行概览</div>
          </div>
        </aside>

        <main className="main-grid">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">总览</h2>
                <p className="panel-subtitle">把最常看的运营数字和错误摘要压缩到一个首页。</p>
              </div>
              <button className="button ghost" onClick={() => void loadAll()} disabled={loading || isRefreshing}>
                {isRefreshing ? "同步中..." : "刷新"}
              </button>
            </div>
            <div className="panel-body">
              <div className="metric-grid">
                <div className="metric-card"><div className="metric-label">注册用户</div><div className="metric-value">{overview?.overview.total_users ?? 0}</div></div>
                <div className="metric-card"><div className="metric-label">累计 LLM 调用</div><div className="metric-value">{overview?.overview.total_llm_calls ?? 0}</div></div>
                <div className="metric-card"><div className="metric-label">未使用邀请码</div><div className="metric-value">{overview?.overview.unused_invite_codes ?? 0}</div></div>
                <div className="metric-card"><div className="metric-label">近 24h 错误</div><div className="metric-value">{overview?.overview.recent_error_count ?? 0}</div></div>
              </div>
              <div className="two-col" style={{ marginTop: 18 }}>
                <div className="data-list">
                  <div className="data-item">
                    <div className="data-title">最近错误事件</div>
                    <div className="data-meta">优先展示高频出错线索，帮助快速判断是鉴权、邀请码还是 LLM 侧异常。</div>
                  </div>
                  {overview?.recent_errors.length ? overview.recent_errors.slice(0, 5).map((item) => (
                    <div className="data-item" key={item.id}>
                      <div className="inline-actions" style={{ justifyContent: "space-between" }}>
                        <span className={`badge ${item.level === "error" ? "error" : ""}`}>{item.category}/{item.event_type}</span>
                        <span className="muted">{new Date(item.created_at).toLocaleString("zh-CN")}</span>
                      </div>
                      <div className="data-meta">{item.message}</div>
                    </div>
                  )) : <div className="empty-state">暂无错误事件</div>}
                </div>
                <div className="data-list">
                  <div className="data-item">
                    <div className="data-title">最近管理员操作</div>
                    <div className="data-meta">邀请码生成、登录和其他后台动作都会落到这里，便于审计。</div>
                  </div>
                  {overview?.recent_admin_actions.length ? overview.recent_admin_actions.slice(0, 5).map((item) => (
                    <div className="data-item" key={item.id}>
                      <div className="inline-actions" style={{ justifyContent: "space-between" }}>
                        <span className="badge">{item.event_type}</span>
                        <span className="muted">{item.username || "-"}</span>
                      </div>
                      <div className="data-meta">{item.message}</div>
                    </div>
                  )) : <div className="empty-state">暂无管理员操作</div>}
                </div>
              </div>
            </div>
          </section>

          <div className="three-col">
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2 className="panel-title">邀请码</h2>
                  <p className="panel-subtitle">第一版支持数量、额度、备注和前缀。</p>
                </div>
              </div>
              <div className="panel-body stack">
                <div>
                  <label className="field-label">生成数量</label>
                  <input className="input" value={inviteCount} onChange={(event) => setInviteCount(event.target.value)} />
                </div>
                <div>
                  <label className="field-label">每个码增加额度</label>
                  <input className="input" value={grantAmount} onChange={(event) => setGrantAmount(event.target.value)} />
                </div>
                <div>
                  <label className="field-label">前缀</label>
                  <input className="input" value={prefix} onChange={(event) => setPrefix(event.target.value)} />
                </div>
                <div>
                  <label className="field-label">备注</label>
                  <textarea className="textarea" value={remark} onChange={(event) => setRemark(event.target.value)} />
                </div>
                {inviteMessage ? <div className={inviteMessage.includes("失败") ? "error-text" : "muted"}>{inviteMessage}</div> : null}
                <button className="button" onClick={handleGenerateInvites} disabled={inviteSubmitting}>
                  {inviteSubmitting ? "生成中..." : "批量生成邀请码"}
                </button>
              </div>
            </section>

            <section className="panel" style={{ gridColumn: "span 2" }}>
              <div className="panel-head">
                <div>
                  <h2 className="panel-title">最近邀请码</h2>
                  <p className="panel-subtitle">用于快速看批次、额度、是否已使用。</p>
                </div>
              </div>
              <div className="panel-body">
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>邀请码</th>
                        <th>额度</th>
                        <th>批次</th>
                        <th>状态</th>
                        <th>备注</th>
                        <th>使用人</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invites.length ? invites.map((item) => (
                        <tr key={`${item.code}-${item.generated_at}`}>
                          <td><strong>{item.code}</strong></td>
                          <td>{item.grant_amount}</td>
                          <td>{item.batch_id}</td>
                          <td><span className={`badge ${item.is_used ? "success" : ""}`}>{item.is_used ? "已使用" : "未使用"}</span></td>
                          <td>{item.remark || "-"}</td>
                          <td>{item.used_by_username || "-"}</td>
                        </tr>
                      )) : (
                        <tr><td colSpan={6}><div className="empty-state">暂无邀请码</div></td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </div>

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">应用日志</h2>
                <p className="panel-subtitle">优先看应用事件，不直接读取服务器文件日志；无设备预览会单独标成 no device preview。</p>
              </div>
            </div>
            <div className="panel-body">
              <div className="toolbar">
                <select className="select" value={logCategory} onChange={(event) => setLogCategory(event.target.value)}>
                  <option value="">全部分类</option>
                  <option value="admin">admin</option>
                  <option value="invite">invite</option>
                  <option value="llm">llm</option>
                </select>
                <select className="select" value={logLevel} onChange={(event) => setLogLevel(event.target.value)}>
                  <option value="">全部级别</option>
                  <option value="info">info</option>
                  <option value="warning">warning</option>
                  <option value="error">error</option>
                </select>
                <input className="input" placeholder="搜索 message / 用户 / MAC / 详情" value={logQuery} onChange={(event) => setLogQuery(event.target.value)} />
                <button className="button secondary" onClick={() => void loadAll({ category: logCategory, level: logLevel, q: logQuery })}>筛选</button>
              </div>
              <div className="inline-actions" style={{ marginBottom: 14 }}>
                <span className="summary-chip">当前日志 {logs.length}</span>
                <span className="summary-chip">涉及用户 {visibleLogUsers.length}</span>
                <span className="summary-chip">No Device Preview {noDevicePreviewCount}</span>
                <span className={`summary-chip ${isRefreshing ? "active" : ""}`}>{isRefreshing ? "实时同步中" : `最近刷新 ${lastUpdatedLabel}`}</span>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>分类</th>
                      <th>事件</th>
                      <th>API</th>
                      <th>Model</th>
                      <th>用户</th>
                      <th>设备</th>
                      <th>Raw Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.length ? logs.map((item) => (
                      <tr key={item.id}>
                        <td>{new Date(item.created_at).toLocaleString("zh-CN")}</td>
                        <td><span className={`badge ${item.level === "error" ? "error" : item.level === "info" ? "success" : ""}`}>{item.category}/{item.level}</span></td>
                        <td>{item.event_type}</td>
                        <td>{item.api_kind || "-"}</td>
                        <td>{item.model_name || "-"}</td>
                        <td>{item.display_username || item.username || "anonymous"}</td>
                        <td>{item.display_mac || (item.is_no_device_preview ? "no device preview" : item.mac || "-")}</td>
                        <td className="raw-message">{item.raw_message || item.message}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={8}><div className="empty-state">暂无日志</div></td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <div className="two-col">
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2 className="panel-title">用户概览</h2>
                  <p className="panel-subtitle">先保留成简表，方便看额度和活跃归属。</p>
                </div>
              </div>
              <div className="panel-body">
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>用户名</th>
                        <th>角色</th>
                        <th>剩余额度</th>
                        <th>累计调用</th>
                        <th>设备数</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.length ? users.map((item) => (
                        <tr key={item.id}>
                          <td>{item.username}</td>
                          <td>{item.role}</td>
                          <td>{item.free_quota_remaining}</td>
                          <td>{item.total_calls_made}</td>
                          <td>{item.device_count}</td>
                        </tr>
                      )) : (
                        <tr><td colSpan={5}><div className="empty-state">暂无用户</div></td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>

            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2 className="panel-title">设备概览</h2>
                  <p className="panel-subtitle">先看 owner、最后模式和渲染量，后面可扩成巡检页。</p>
                </div>
              </div>
              <div className="panel-body">
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>MAC</th>
                        <th>Owner</th>
                        <th>最后模式</th>
                        <th>渲染数</th>
                        <th>最后刷新</th>
                      </tr>
                    </thead>
                    <tbody>
                      {devices.length ? devices.map((item) => (
                        <tr key={item.mac}>
                          <td>{item.mac}</td>
                          <td>{item.owner_username || "-"}</td>
                          <td>{item.last_persona || "-"}</td>
                          <td>{item.total_renders}</td>
                          <td>{item.last_refresh_at ? new Date(item.last_refresh_at).toLocaleString("zh-CN") : "-"}</td>
                        </tr>
                      )) : (
                        <tr><td colSpan={5}><div className="empty-state">暂无设备</div></td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
