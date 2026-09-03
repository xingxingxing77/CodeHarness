"use client";

/**
 * AppSidebar：分组式导航（可折叠树 / 徽标 / 快捷键提示）。
 * 顶部 switcher 插槽由宿主注入（真实工作区切换器）；数据：Inbox 徽标 = 待审批数，
 * 后端没有的项标记 soon（降透明+跳占位页）。
 */

import { useState } from "react";
import {
  Activity,
  Brain,
  Calendar,
  ChevronRight,
  CreditCard,
  FolderKanban,
  Globe,
  Hash,
  LogOut,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
} from "lucide-react";

export type NavItemData = {
  id: string;
  title: string;
  icon: React.ElementType;
  badge?: number | string;
  shortcut?: string;
  href?: string;
  soon?: boolean;
  children?: NavItemData[];
};

export type NavGroupData = { heading?: string; items: NavItemData[] };

export function buildNavGroups(pendingApprovals: number): NavGroupData[] {
  return [
    {
      items: [
        { id: "search", title: "Search", icon: Search, shortcut: "⌘K" },
        { id: "/approvals", title: "Inbox", icon: ShieldCheck, badge: pendingApprovals || undefined, href: "/approvals" },
        { id: "/analytics", title: "Analytics", icon: Activity, soon: true },
      ],
    },
    {
      heading: "Workspace",
      items: [
        { id: "/skills", title: "Skills", icon: Sparkles, href: "/skills" },
        { id: "/memories", title: "Memories", icon: Brain, href: "/memories" },
        {
          id: "/projects",
          title: "Projects",
          icon: FolderKanban,
          soon: true,
          children: [
            { id: "p-active", title: "Active", icon: Hash, soon: true },
            { id: "p-archived", title: "Archived", icon: Hash, soon: true },
          ],
        },
        { id: "/calendar", title: "Calendar", icon: Calendar, soon: true },
        {
          id: "/team",
          title: "Team",
          icon: Globe,
          soon: true,
          children: [{ id: "t-members", title: "Members", icon: Hash, soon: true }],
        },
        { id: "/finance", title: "Usage & Billing", icon: CreditCard, soon: true },
      ],
    },
    {
      heading: "Developers",
      items: [{ id: "/credentials", title: "API Keys", icon: Terminal, href: "/credentials" }],
    },
  ];
}

const WORKSPACE = { name: "Codeharness" };

function CollapsedWorkspaceMark() {
  return (
    <div className="mb-2 flex h-10 items-center justify-center">
      <span className="flex size-8 items-center justify-center rounded-[6px] bg-accent text-[13px] font-semibold text-white shadow-card">
        C
      </span>
    </div>
  );
}

function NavItem({
  item,
  activeId,
  onSelect,
  onNavigate,
  level = 0,
  collapsed = false,
}: {
  item: NavItemData;
  activeId: string;
  onSelect: (id: string) => void;
  onNavigate?: (href: string) => void;
  level?: number;
  collapsed?: boolean;
}) {
  const isActive = activeId === item.id;
  const hasChildren = !!item.children;
  const [open, setOpen] = useState(false);

  const handleClick = () => {
    if (item.href) {
      onNavigate?.(item.href);
      onSelect(item.id);
      return;
    }
    if (hasChildren) setOpen(!open);
    else onSelect(item.id);
  };

  if (collapsed && !hasChildren && level === 0) {
    return (
      <div className="flex w-full justify-center py-0.5" title={item.title + (item.soon ? "（即将上线）" : "")}>
        <button
          onClick={handleClick}
          className={`flex size-8 items-center justify-center rounded-[6px] transition-colors ${
            isActive ? "bg-hover-2 text-ink" : "text-ink-2 hover:bg-hover hover:text-ink"
          } ${item.soon ? "opacity-40" : ""}`}
        >
          <item.icon className="size-4" strokeWidth={1.5} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col">
      <div
        onClick={handleClick}
        title={item.soon ? `${item.title}（即将上线）` : item.title}
        className={`group flex cursor-pointer select-none items-center justify-between rounded-[6px] px-2.5 py-[7px] transition-all duration-200
          ${isActive ? "bg-hover-2 font-medium text-ink" : "text-ink-2 hover:bg-hover hover:text-ink"}
          ${item.soon ? "opacity-45" : ""}
        `}
        style={{ paddingLeft: `${level * 12 + 10}px` }}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <item.icon
            className={`size-4 shrink-0 transition-colors ${isActive ? "text-ink" : "text-ink-3 group-hover:text-ink-2"}`}
            strokeWidth={1.5}
          />
          <span className="truncate text-[13px] tracking-wide">{item.title}</span>
        </div>

        <div className="flex items-center gap-2">
          {item.shortcut && (
            <kbd className="hidden h-5 items-center rounded-[4px] border border-line bg-surface px-1.5 font-mono text-[10px] text-ink-3 shadow-hairline group-hover:inline-flex">
              {item.shortcut}
            </kbd>
          )}
          {item.badge !== undefined && (
            <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-accent-tint px-1.5 text-[10px] font-medium text-accent-ink">
              {item.badge}
            </span>
          )}
          {hasChildren && (
            <ChevronRight
              className={`size-3.5 text-ink-3 transition-transform duration-200 ${open ? "rotate-90" : ""}`}
              strokeWidth={2}
            />
          )}
        </div>
      </div>

      {hasChildren && (
        <div
          className={`grid transition-[grid-template-rows,opacity] duration-300 ${
            open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
          }`}
        >
          <div className="relative mt-0.5 flex min-h-0 flex-col gap-0.5 overflow-hidden">
            <div className="absolute bottom-0 top-0 border-l border-line" style={{ left: `${level * 12 + 17.5}px` }} />
            {item.children!.map((child) => (
              <NavItem
                key={child.id}
                item={child}
                activeId={activeId}
                onSelect={onSelect}
                onNavigate={onNavigate}
                level={level + 1}
                collapsed={collapsed}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function AppSidebar({
  groups,
  activeId,
  onSelect,
  onNavigate,
  collapsed = false,
  bottomItems = [],
  switcher,
}: {
  groups: NavGroupData[];
  activeId: string;
  onSelect: (id: string) => void;
  onNavigate?: (href: string) => void;
  collapsed?: boolean;
  bottomItems?: NavItemData[];
  switcher?: React.ReactNode;
}) {
  return (
    <div className="flex h-full w-full flex-col gap-3 p-3">
      {collapsed ? <CollapsedWorkspaceMark /> : switcher}

      <div className="mt-1 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {groups.map((group, idx) => (
          <div key={idx} className="flex flex-col gap-0.5">
            {group.heading && !collapsed && (
              <span className="mb-1 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                {group.heading}
              </span>
            )}
            {group.items.map((item) => (
              <NavItem
                key={item.id}
                item={item}
                activeId={activeId}
                onSelect={onSelect}
                onNavigate={onNavigate}
                collapsed={collapsed}
              />
            ))}
          </div>
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-0.5 border-t border-line pt-3">
        {bottomItems.map((item) => (
          <NavItem key={item.id} item={item} activeId={activeId} onSelect={onSelect} onNavigate={onNavigate} collapsed={collapsed} />
        ))}
        {collapsed && (
          <div className="flex w-full justify-center py-1">
            <button
              onClick={() => onNavigate?.("/settings")}
              title="Settings"
              className="flex size-8 items-center justify-center rounded-[6px] text-ink-2 hover:bg-hover hover:text-ink"
            >
              <LogOut className="size-4" strokeWidth={1.5} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
