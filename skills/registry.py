"""skills/：SKILL.md 技能加载器（后端设计 §7.10）。

技能目录结构：{skills_root}/{skill_name}/SKILL.md（frontmatter: name/description）。
加载器扫描目录 → SkillRegistry：list/get；M1 供 REST /skills 与 @ 引用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: str


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)


def _parse_skill(path: Path) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    name = path.parent.name
    description = ""
    body = text
    match = _FRONTMATTER.match(text)
    if match:
        body = text[match.end():]
        for line in match.group(1).splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip() or name
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
    if not body.strip():
        return None
    return Skill(name=name, description=description, body=body, path=str(path))


class SkillRegistry:
    def __init__(self, roots: list[str]) -> None:
        self._roots = [Path(r) for r in roots]
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        for root in self._roots:
            if not root.exists():
                continue
            for path in sorted(root.glob("*/SKILL.md")):
                skill = _parse_skill(path)
                if skill is not None and skill.name not in self._skills:
                    self._skills[skill.name] = skill

    def list(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)
