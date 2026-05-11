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
		<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-4 backdrop-blur">
			<p className="text-xs uppercase tracking-[0.16em] text-cyan-300/55">Filters</p>
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
									? "border-cyan-400/50 bg-cyan-500/20 text-cyan-100"
									: "border-cyan-500/28 text-cyan-100/65 hover:border-cyan-400/55 hover:text-cyan-100"
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
