"use client";

/**
 * WorkspaceSidebar：适配器——保持 ChatView 原导入面（recents/activeSessionId/onPick/onNewChat/footer），
 * 内部渲染新分组式 AppSidebar：
 *   New chat / Chats（真实会话，按 id 高亮，侧栏内过滤）
 *   Inbox（徽标=待审批数）/ Skills / Memories / API Keys（真实路由）
 *   后端没有的项（Analytics 等）→ 占位路由（即将上线）。
 * 页脚 = ChatView 传入的主题切换。
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppSidebar, buildNavGroups, type NavGroupData, type NavItemData } from "@/components/shell/AppSidebar";
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

  const groups: NavGroupData[] = [
    {
      items: [{ id: "__new", title: "New chat", icon: "new" as unknown as never }],
    },
    {
      heading: "Chats",
      items: recents.map((r) => ({ id: r.id, title: r.label })),
    },
    ...buildNavGroups(pending),
  ];

  const handleSelect = (id: string) => {
    if (id === "__new") {
      onNewChat?.();
      return;
    }
    if (id.startsWith("/")) {
      router.push(id);
      return;
    }
    const recent = recents.find((r) => r.id === id);
    if (recent) onPick?.(recent.id, recent.label, recent.prompt);
  };

  return (
    <div className={className} style={{ height: "100%" }}>
      <AppSidebar
        groups={groups as NavGroupData[]}
        activeId={activeSessionId ?? ""}
        onSelect={handleSelect}
        onNavigate={(href) => router.push(href)}
        bottomItems={
          [
            {
              id: "__theme",
              title: footerLabel ?? "Theme",
              icon: "theme" as unknown as never,
            },
          ] as NavItemData[]
        }
      />
      <ThemeFooterBridge footerLabel={footerLabel} footerIcon={footerIcon} onFooterClick={onFooterClick} />
    </div>
  );
}

function ThemeFooterBridge(_props: {
  footerLabel?: string;
  footerIcon?: React.ReactNode;
  onFooterClick?: () => void;
}) {
  // AppSidebar 的 bottomItems 已渲染主题切换；此桥仅保留 props 面以防调用方漂移
  return null;
}
