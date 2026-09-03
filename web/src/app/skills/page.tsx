"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Skill } from "@/lib/types";

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listSkills().then((rows) => {
      setSkills(rows);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="p-4 text-ink-2">Loading skills...</div>;

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold text-ink">Skills</h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {skills.map((skill) => (
          <div key={skill.id} className="rounded-card border border-line bg-surface p-4 shadow-sm transition-shadow hover:shadow-md">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-medium text-ink">{skill.name}</span>
              <span className="text-xs text-ink-3">{skill.version}</span>
            </div>
            <p className="text-sm text-ink-2">{skill.description || "No description provided."}</p>
            <div className="mt-3 flex items-center gap-2">
              <span className="rounded-full bg-blue-tint px-2 py-0.5 text-[10px] font-medium text-blue-ink">
                {skill.category || "General"}
              </span>
              {skill.enabled === false && (
                <span className="rounded-full bg-red-tint px-2 py-0.5 text-[10px] font-medium text-red-ink">
                  Disabled
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
