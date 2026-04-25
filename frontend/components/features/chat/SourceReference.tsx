"use client";

import { FileText, FolderTree } from "lucide-react";

import type { ChatSources } from "@/types";

interface SourceReferenceProps {
	sources?: ChatSources | null;
}

export function SourceReference({ sources }: SourceReferenceProps) {
	const documents = sources?.documents ?? [];
	const chunks = sources?.chunks ?? [];

	if (documents.length === 0 && chunks.length === 0) {
		return null;
	}

	return (
		<div className="mt-3 rounded-xl border border-zinc-800 bg-zinc-900/70 p-3">
			<p className="text-[11px] uppercase tracking-[0.16em] text-zinc-400">Source References</p>

			<div className="mt-2 space-y-2">
				{documents.map((document) => (
					<div
						key={`${document.document_id}-${document.title}`}
						className="flex items-center justify-between gap-3 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5"
					>
						<div className="flex min-w-0 items-center gap-2">
							<FileText className="h-3.5 w-3.5 flex-shrink-0 text-zinc-400" />
							<p className="truncate text-xs text-zinc-100">{document.title}</p>
						</div>
						<div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-zinc-400">
							<span>{document.chunk_count} chunks</span>
							<span>score {document.max_score.toFixed(2)}</span>
						</div>
					</div>
				))}
			</div>

			{chunks.length > 0 ? (
				<details className="mt-3 rounded-md border border-zinc-800 bg-zinc-950 p-2">
					<summary className="cursor-pointer text-xs text-zinc-300">
						Preview Supporting Chunks ({Math.min(chunks.length, 3)})
					</summary>
					<div className="mt-2 space-y-2">
						{chunks.slice(0, 3).map((chunk) => (
							<div
								key={`${chunk.chunk_id}-${chunk.chunk_index}`}
								className="rounded-md border border-zinc-800 bg-zinc-900/70 p-2"
							>
								<div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-zinc-400">
									<FolderTree className="h-3 w-3" />
									<span>{chunk.document_title}</span>
									<span>chunk {chunk.chunk_index}</span>
								</div>
								<p className="mt-1 text-xs text-zinc-300">{chunk.preview}</p>
							</div>
						))}
					</div>
				</details>
			) : null}
		</div>
	);
}
