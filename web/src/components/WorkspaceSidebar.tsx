"use client";

/**
 * WorkspaceSidebar：适配器——保持 ChatView 原导入面（recents/activeSessionId/onPick/onNewChat/footer），
 * 内部渲染新分组式 AppSidebar：
 *   New chat / Chats（真实会话，按 id 高亮）
 *   Inbox（徽标=待审批数）/ Skills / Memories / API Keys（真实路由）
 *   Analytics/Projects/Calendar/Team/Billing（占位路由，即将上线）
 * 页脚 = ChatView 传入的主题切换。
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Hash, SquarePen } from "lucide-react";

import { AppSidebar, buildNavGroups, type NavGroupData } from "@/components/shell/AppSidebar";
import { api } from "@/lib/api";
import type { Session } from "@/lib/types";

export type SidebarRecent = { id: string; label: string; prompt?: string };

type WorkspaceSidebarProps = {
  activeTitle?: string | null;
  className?: string;
  fill?: boolean;
  onNewChat?: () => void;
  onPick?: (id: string, label: string, prompt?: string) => void;
  activeNav?: string;
  onNavigate?: (key: string) => void;
  footerLabel?: string;
  footerIcon?: React.ReactNode;
  onFooterClick?: () => void;
  recents?: SidebarRecent[];
  activeSessionId?: string | null;
};

export default function WorkspaceSidebar({
  onNewChat,
  onPick,
  activeSessionId = null,
  footerLabel,
  footerIcon,
  onFooterClick,
  recents = [],
  className = "",
}: WorkspaceSidebarProps) {
  const router = useRouter();
  const [pending, setPending] = useState(0);

  useEffect(() => {
    api
      .listApprovals()
      .then((rows) => setPending(rows.length))
      .catch(() => undefined);
  }, [recents.length]);

  const chatItems = recents.map((r) => ({ id: r.id, title: r.label, icon: Hash }));

  const groups: NavGroupData[] = [
    {
      items: [{ id: "__new", title: "New chat", icon: SquarePen }],
    },
    {
      heading: "Chats",
      items: chatItems,
    },
    ...buildNavGroups(pending),
  ];

  const handleSelect = (id: string) => {
    if (id === "__new") {
      onNewChat?.();
      return;
    }
    if (id === "__theme") {
      onFooterClick?.();
      return;
    }
    if (id.startsWith("/")) {
      router.push(id);
      return;
    }
    const recent = recents.find((r) => r.id === id);
    if (recent) onPick?.(recent.id, recent.label, recent.prompt);
  };

  const bottomItems = [
    {
      id: "__theme",
      title: footerLabel ?? "Theme",
      icon: footerIcon ?? undefined,
    },
  ] as unknown as NavGroupData["items"];

  return (
    <div className={className} style={{ height: "100%" }}>
      <div className="flex items-center gap-2.5 px-3 pb-2 pt-3">
        <div className="flex size-8 items-center justify-center rounded-[6px] bg-accent text-[13px] font-semibold text-white shadow-card">
          C
        </div>
        <div className="flex flex-col overflow-hidden">
          <span className="truncate text-[13px] font-medium leading-none text-ink">Codeharness</span>
          <span className="text-[11px] leading-none text-ink-3">Platform</span>
        </div>
      </div>
      <AppSidebar
        groups={groups}
        activeId={activeSessionId ?? ""}
        onSelect={handleSelect}
        onNavigate={(href) => router.push(href)}
        bottomItems={bottomItems}
      />
    </div>
  );
}
