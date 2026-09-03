"use client";

export default function FinancePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-6 text-center">
      <div className="text-4xl">💳</div>
      <h1 className="text-xl font-semibold text-ink">Usage & Billing</h1>
      <p className="text-sm text-ink-2 max-w-md">
        Track your API usage, manage subscriptions, and view billing history.
      </p>
    </div>
  );
}
