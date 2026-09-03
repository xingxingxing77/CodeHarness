"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Skill = { name: string; description: string };

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listSkills()
      .then(setSkills)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 text-[13px] text-ink-2">Loading skills…</div>;
  if (error) return <div className="p-6 text-[13px] text-red">Failed to load skills: {error}</div>;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Skills</h1>
        <p className="text-sm text-ink-2">Capabilities registered in the skill registry.</p>
      </div>
      {skills.length === 0 ? (
        <div className="rounded-card border border-line bg-surface p-8 text-center text-ink-2">
          No skills registered.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill) => (
            <div
              key={skill.name}
              className="rounded-card border border-line bg-surface p-4 shadow-sm transition-shadow hover:shadow-md"
            >
              <span className="text-[14px] font-medium text-ink">{skill.name}</span>
              <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">
                {skill.description || "No description provided."}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
