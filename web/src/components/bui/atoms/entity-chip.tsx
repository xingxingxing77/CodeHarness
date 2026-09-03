/**
 * EntityChip / ValuePill 原子（J24 本地化）。
 * 消费方：recommendation-card 建议正文中的实体与取值强调。
 */
/** 实体强调片（accent 色系）。 */
export function EntityChip({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-[5px] bg-accent-tint px-1.5 py-0.5 align-baseline text-[12px] font-medium text-accent-ink">
      <span className="size-1.5 rounded-full bg-accent" />
      {name}
    </span>
  );
}

/** 取值药丸（tone=green 时语义强调）。 */
export function ValuePill({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone?: "green";
}) {
  return (
    <span
      className={`inline-flex h-5 items-center rounded-full px-2 align-baseline text-[11.5px] font-medium shadow-hairline ${
        tone === "green" ? "bg-green-tint text-green" : "bg-inset text-ink-2"
      }`}
    >
      {children}
    </span>
  );
}
