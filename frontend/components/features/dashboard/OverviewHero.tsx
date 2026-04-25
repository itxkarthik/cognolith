"use client";

export function OverviewHero() {
  const cards = [
    { label: "Total Notes", value: 0 },
    { label: "Total Documents", value: 0 },
    { label: "Quick Actions", value: 5 },
  ];

  return (
    <section className="rounded-2xl border border-[#464554]/20 bg-[#1f1f1f] p-6">
      <p className="text-xs uppercase tracking-[0.25em] text-[#908fa0]">
        Overview
      </p>
      <h1 className="mt-2 text-3xl font-black text-[#e2e2e2] tracking-tight">
        Your Knowledge Hub
      </h1>
      <p className="mt-2 max-w-2xl text-[#c7c4d7]">
        Keep everything in one place: notes, documents, and AI conversations.
      </p>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-[#464554]/20 bg-[#131313] p-4"
          >
            <p className="text-xs uppercase tracking-[0.18em] text-[#908fa0]">
              {card.label}
            </p>
            <p className="mt-2 text-3xl font-black text-[#bcff5f]">
              {card.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
