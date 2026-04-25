"use client";

import type { SearchEntityType } from "@/lib/api/search";

interface SearchFiltersProps {
	selectedTypes: SearchEntityType[];
	onToggleType: (type: SearchEntityType) => void;
}

const SEARCH_TYPES: Array<{ id: SearchEntityType; label: string }> = [
	{ id: "document", label: "Documents" },
	{ id: "note", label: "Notes" },
	{ id: "chat", label: "Chats" },
];

export function SearchFilters({ selectedTypes, onToggleType }: SearchFiltersProps) {
	return (
		<section className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4 backdrop-blur">
			<p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Filters</p>
			<div className="mt-2 flex flex-wrap items-center gap-2">
				{SEARCH_TYPES.map((type) => {
					const isSelected = selectedTypes.includes(type.id);
					return (
						<button
							key={type.id}
							type="button"
							onClick={() => onToggleType(type.id)}
							className={`rounded-lg border px-3 py-1.5 text-xs uppercase tracking-[0.12em] transition ${
								isSelected
									? "border-zinc-600 bg-zinc-800 text-zinc-100"
									: "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
							}`}
						>
							{type.label}
						</button>
					);
				})}
			</div>
		</section>
	);
}
