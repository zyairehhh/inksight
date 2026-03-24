"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

export function AdminLoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/admin/auth/me", { cache: "no-store" })
      .then((res) => {
        if (res.ok) router.replace("/");
      })
      .catch(() => undefined);
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch("/api/admin/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body.error === "string" ? body.error : "登录失败，请检查配置和凭据");
        return;
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="admin-login-shell">
      <div className="admin-login-card">
        <p className="eyebrow">InkSight Admin Console</p>
        <h1 className="hero-title">管理后台</h1>
        <p className="hero-text">
          独立运营面板，用于邀请码生成、指标概览、日志排查和基础运维观察。
        </p>

        <form onSubmit={handleSubmit} className="stack" style={{ marginTop: 24 }}>
          <div>
            <label className="field-label" htmlFor="username">管理员账号</label>
            <input
              id="username"
              className="input"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="输入管理员用户名"
            />
          </div>
          <div>
            <label className="field-label" htmlFor="password">管理员密码</label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="输入管理员密码"
            />
          </div>
          {error ? <div className="error-text">{error}</div> : null}
          <button className="button" type="submit" disabled={submitting || !username || !password}>
            {submitting ? "登录中..." : "进入管理台"}
          </button>
        </form>
      </div>
    </div>
  );
}
