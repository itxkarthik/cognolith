"use client";

import { FileText, MessageSquare, NotebookPen, Search } from "lucide-react";
import Link from "next/link";

import type { SearchResultItem } from "@/types";

interface SearchResultsProps {
	query: string;
	results: SearchResultItem[];
	total: number;
	isLoading?: boolean;
}

function getEntityMeta(entityType: SearchResultItem["entity_type"]) {
	if (entityType === "document") {
		return {
			label: "Document",
			icon: FileText,
			href: "/dashboard/documents",
		};
	}

	if (entityType === "note") {
		return {
			label: "Note",
			icon: NotebookPen,
			href: "/dashboard/notes",
		};
	}

	return {
		label: "Chat",
		icon: MessageSquare,
		href: "/dashboard/chat",
	};
}

export function SearchResults({
	query,
	results,
	total,
	isLoading = false,
}: SearchResultsProps) {
	if (isLoading) {
		return (
			<section className="space-y-2">
				{Array.from({ length: 8 }).map((_, index) => (
					<div
						key={index}
						className="h-20 animate-pulse rounded-xl border border-zinc-800 bg-[#0f1930]/80"
					/>
				))}
			</section>
		);
	}

	if (!query.trim()) {
		return (
			<section className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-5 text-sm text-zinc-400">
				Run a search to scan documents, notes, and chats in one place.
			</section>
		);
	}

	if (results.length === 0) {
		return (
			<section className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-5 text-sm text-zinc-400">
				No results found for {query}.
			</section>
		);
	}

	return (
		<section className="space-y-3">
			<p className="text-xs uppercase tracking-[0.16em] text-zinc-500">
				{total} {total === 1 ? "result" : "results"}
			</p>

			{results.map((result) => {
				const meta = getEntityMeta(result.entity_type);
				const EntityIcon = meta.icon;
				const href =
					result.entity_type === "chat"
						? `${meta.href}/${result.id}`
						: meta.href;

				return (
					<Link
						key={`${result.entity_type}-${result.id}-${result.updated_at ?? ""}`}
						href={href}
						className="block rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-4 transition hover:border-zinc-600"
					>
						<div className="flex items-start justify-between gap-3">
							<div className="min-w-0">
								<div className="flex items-center gap-2 text-xs uppercase tracking-[0.12em] text-zinc-500">
									<EntityIcon className="h-3.5 w-3.5" />
									<span>{meta.label}</span>
								</div>
								<h3 className="mt-1 line-clamp-1 text-sm font-semibold text-zinc-100">
									{result.title || "Untitled"}
								</h3>
								<p className="mt-1 line-clamp-2 text-xs text-zinc-400">
									{result.snippet || "No preview available"}
								</p>
							</div>

							<div className="flex-shrink-0 text-[11px] uppercase tracking-[0.1em] text-zinc-500">
								<Search className="h-4 w-4" />
							</div>
						</div>
					</Link>
				);
			})}
		</section>
	);
}
