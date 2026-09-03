"""prompts/：system prompt 编织服务（后端设计 §7.7，P3）。

模板分节：身份 → 能力指引 → 工作区规则 → 个性化。会话状态（目标/模式）
由调用方注入 sections。编织语义保留 OpenHarness 思路：分节拼接、空节跳过。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from state.session_state import SessionState


@dataclass
class PromptComposer:
    identity: str = "You are Codeharness, a capable coding agent."
    guidance: str = (
        "Work step by step. Prefer reading before writing. "
        "Use tools to inspect the workspace instead of guessing."
    )
    workspace_rules: str = (
        "All file operations happen inside the session workspace. "
        "Paths outside the workspace are rejected."
    )
    personalization: str = ""
    extra_sections: list[str] = field(default_factory=list)

    def compose(self, state: SessionState | None = None) -> str:
        sections = [self.identity, self.guidance, self.workspace_rules]
        if self.personalization:
            sections.append(self.personalization)
        if state is not None:
            if state.goal:
                sections.append(f"Current goal: {state.goal}")
            if state.permission_mode and state.permission_mode != "default":
                sections.append(f"Permission mode: {state.permission_mode}")
        sections.extend(s for s in self.extra_sections if s.strip())
        return "\n\n".join(s for s in sections if s)
