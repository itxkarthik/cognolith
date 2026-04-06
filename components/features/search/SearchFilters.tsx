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
		<section className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-3">
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
									? "border-[#94aaff]/50 bg-[#94aaff]/10 text-[#dce6ff]"
									: "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
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
