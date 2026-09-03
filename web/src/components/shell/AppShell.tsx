"use client";

/** 应用壳：分组侧栏 + 折叠开关 + 面包屑头部 + ⌘K 命令面板 + 子页容器。 */

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen, Search, X } from "lucide-react";

import { api } from "@/lib/api";
import { AppSidebar, buildNavGroups } from "@/components/shell/AppSidebar";
import type { Session } from "@/lib/types";

export const PLACEHOLDER_TITLES: Record<string, string> = {
  "/analytics": "Analytics",
  "/calendar": "Calendar",
  "/team": "Team",
  "/finance": "Usage & Billing",
  "/projects": "Projects",
  "/webhooks": "Webhooks",
  "/settings": "Settings",
};

function titleForPath(pathname: string, sessions: Session[]): string {
  if (PLACEHOLDER_TITLES[pathname]) return PLACEHOLDER_TITLES[pathname];
  const named: Record<string, string> = {
    "/approvals": "Inbox · Approvals",
    "/skills": "Skills",
    "/memories": "Memories",
    "/credentials": "API Keys",
  };
  if (named[pathname]) return named[pathname];
  if (pathname.startsWith("/sessions/")) {
    const s = sessions.find((x) => x.id === pathname.split("/")[2]);
    return s ? s.title || s.id.slice(0, 8) : "Chat";
  }
  return "Home";
}

function activeNavId(pathname: string): string {
  if (PLACEHOLDER_TITLES[pathname]) return pathname;
  const named: Record<string, string> = {
    "/approvals": "/approvals",
    "/skills": "/skills",
    "/memories": "/memories",
    "/credentials": "/credentials",
  };
  if (named[pathname]) return named[pathname];
  return "chats";
}

const PALETTE_ACTIONS: { label: string; href: string }[] = [
  { label: "Inbox · Approvals", href: "/approvals" },
  { label: "Skills", href: "/skills" },
  { label: "Memories", href: "/memories" },
  { label: "API Keys", href: "/credentials" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [pending, setPending] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.listSessions().then(setSessions).catch(() => undefined);
    api
      .listApprovals()
      .then((rows) => setPending(rows.length))
      .catch(() => undefined);
  }, [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const groups = useMemo(() => buildNavGroups(pending), [pending]);
  const activeId = activeNavId(pathname);
  const title = titleForPath(pathname, sessions);

  const sessionEntries = sessions.slice(0, 5).map((s) => ({
    label: `↳ ${s.title || s.id.slice(0, 8)}`,
    href: `/sessions/${s.id}`,
  }));
  const paletteActions = [...PALETTE_ACTIONS, ...sessionEntries];
  const filtered = paletteActions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()));

  const navigate = (href: string) => {
    setPaletteOpen(false);
    router.push(href);
  };

  return (
    <div className="flex h-dvh overflow-hidden bg-page">
      <div
        className="shrink-0 overflow-hidden border-r border-line bg-surface transition-[width] duration-300"
        style={{ width: collapsed ? 64 : 248 }}
      >
        <AppSidebar
          groups={groups}
          activeId={activeId}
          onSelect={(id) => {
            if (id.startsWith("/")) navigate(id);
          }}
          onNavigate={navigate}
          collapsed={collapsed}
          bottomItems={[{ id: "settings", title: "Settings", icon: Search, shortcut: "⌘,", href: "/settings" }]}
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-line bg-surface px-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setCollapsed((v) => !v)}
              className="rounded-[6px] p-1.5 text-ink-3 transition-colors hover:bg-hover hover:text-ink"
              aria-label="Toggle sidebar"
            >
              {collapsed ? <PanelLeftOpen className="size-[18px]" strokeWidth={1.5} /> : <PanelLeftClose className="size-[18px]" strokeWidth={1.5} />}
            </button>
            <div className="flex items-center gap-2 text-[13px] text-ink-2">
              <span className="truncate">Codeharness</span>
              <span>/</span>
              <span className="truncate font-medium text-ink">{title}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setPaletteOpen(true)}
              className="hidden items-center gap-2 rounded-[6px] border border-line bg-field px-2 py-1 text-[12px] text-ink-3 hover:text-ink-2 md:flex"
            >
              <Search className="size-3.5" />
              Search…
              <kbd className="rounded-[4px] border border-line px-1 font-mono text-[10px]">⌘K</kbd>
            </button>
            <div className="flex size-7 items-center justify-center rounded-full border border-accent/30 bg-accent-tint text-[11px] font-semibold text-accent-ink">
              OP
            </div>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </div>

      {paletteOpen && (
        <div className="absolute inset-0 z-50 flex items-start justify-center bg-black/20 px-4 pt-[15vh] backdrop-blur-sm">
          <div className="absolute inset-0" onClick={() => setPaletteOpen(false)} />
          <div
            className="relative w-full max-w-xl overflow-hidden rounded-[10px] border border-line bg-surface shadow-raised"
            style={{ animation: "pop-in 180ms cubic-bezier(0.23,1,0.32,1) both" }}
          >
            <div className="flex items-center border-b border-line px-4">
              <Search className="mr-3 size-[18px] shrink-0 text-ink-3" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search sessions, pages, or actions..."
                className="flex-1 bg-transparent py-3.5 text-[14px] text-ink outline-none placeholder:text-ink-3"
              />
              <button onClick={() => setPaletteOpen(false)} className="ml-3 rounded-[6px] p-1 text-ink-3 hover:bg-hover hover:text-ink">
                <X className="size-[18px]" />
              </button>
            </div>
            <div className="flex max-h-[320px] flex-col overflow-y-auto p-1.5">
              {filtered.map((a) => (
                <button
                  key={a.label}
                  onClick={() => navigate(a.href)}
                  className="rounded-[8px] px-3 py-2.5 text-left text-[13px] text-ink transition-colors hover:bg-hover"
                >
                  {a.label}
                </button>
              ))}
              {filtered.length === 0 && (
                <div className="flex flex-col items-center gap-2 py-8 text-ink-3">
                  <Search className="size-6" />
                  <p className="text-[13px]">No matches</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
