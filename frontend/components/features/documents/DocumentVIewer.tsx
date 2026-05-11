"use client";

import { Clock3, ExternalLink, FileText, Languages, Trash2 } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils/cn";
import type { DocumentResponse } from "@/types";

import {
	formatBytes,
	formatDate,
	formatFileType,
	getStatusClasses,
} from "./utils";

interface DocumentViewerProps {
	document: DocumentResponse;
	onDelete?: (id: number) => Promise<void> | void;
	isDeleting?: boolean;
}

export function DocumentViewer({
	document,
	onDelete,
	isDeleting = false,
}: DocumentViewerProps) {
	const handleDeleteClick = async () => {
		if (!onDelete || isDeleting) {
			return;
		}

		const confirmed = window.confirm(
			`Delete document \"${document.title}\"? This action cannot be undone.`
		);
		if (!confirmed) {
			return;
		}

		await onDelete(document.id);
	};

	return (
		<div className="space-y-6">
			<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6">
				<div className="flex flex-wrap items-start justify-between gap-4">
					<div>
						<p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-cyan-300/55">
							<FileText className="h-3.5 w-3.5" />
							{formatFileType(document.file_type)}
						</p>
						<h1 className="mt-2 text-3xl font-semibold text-cyan-50">{document.title}</h1>
						<p className="mt-2 inline-flex items-center gap-1.5 text-sm text-cyan-100/65">
							<Clock3 className="h-4 w-4" />
							Updated {formatDate(document.updated_at)}
						</p>
					</div>

					<div className="flex flex-wrap items-center gap-2">
						<span
							className={cn(
								"rounded-full border px-2 py-1 text-xs font-medium capitalize",
								getStatusClasses(document.status)
							)}
						>
							{document.status}
						</span>
						<Link
							href={`/dashboard/documents/${document.id}/full-text`}
							target="_blank"
							rel="noopener noreferrer"
							className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 px-3 py-2 text-sm text-cyan-100 transition hover:border-cyan-400/55"
						>
							<ExternalLink className="h-4 w-4" />
							Open Full Text
						</Link>
						<button
							type="button"
							onClick={() => {
								void handleDeleteClick();
							}}
							disabled={!onDelete || isDeleting}
							className="inline-flex items-center gap-2 rounded-lg border border-rose-800/70 px-3 py-2 text-sm text-rose-200 transition hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-50"
						>
							<Trash2 className="h-4 w-4" />
							{isDeleting ? "Deleting..." : "Delete"}
						</button>
					</div>
				</div>

				<div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
					<div className="rounded-xl border border-cyan-500/20 bg-[#01040f] p-3">
						<p className="text-xs uppercase tracking-[0.14em] text-cyan-300/55">File Name</p>
						<p className="mt-1 line-clamp-1 text-sm text-cyan-100">{document.file_name}</p>
					</div>
					<div className="rounded-xl border border-cyan-500/20 bg-[#01040f] p-3">
						<p className="text-xs uppercase tracking-[0.14em] text-cyan-300/55">Size</p>
						<p className="mt-1 text-sm text-cyan-100">{formatBytes(document.file_size)}</p>
					</div>
					<div className="rounded-xl border border-cyan-500/20 bg-[#01040f] p-3">
						<p className="text-xs uppercase tracking-[0.14em] text-cyan-300/55">Chunks</p>
						<p className="mt-1 text-sm text-cyan-100">{document.chunk_count}</p>
					</div>
					<div className="rounded-xl border border-cyan-500/20 bg-[#01040f] p-3">
						<p className="text-xs uppercase tracking-[0.14em] text-cyan-300/55">Language</p>
						<p className="mt-1 inline-flex items-center gap-1.5 text-sm text-cyan-100">
							<Languages className="h-3.5 w-3.5" />
							{document.language}
						</p>
					</div>
				</div>
			</section>

			{document.summary ? (
				<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6">
					<h2 className="text-lg font-semibold text-cyan-50">Summary</h2>
					<p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-cyan-100/70">
						{document.summary}
					</p>
				</section>
			) : null}

			<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6">
				<h2 className="text-lg font-semibold text-cyan-50">Content Preview</h2>
				{document.content_preview ? (
					<p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-cyan-100/70">
						{document.content_preview}
					</p>
				) : (
					<p className="mt-3 text-sm text-cyan-100/60">
						No preview is available for this document yet.
					</p>
				)}
			</section>

			{document.tags.length > 0 ? (
				<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6">
					<h2 className="text-lg font-semibold text-cyan-50">Tags</h2>
					<div className="mt-3 flex flex-wrap gap-2">
						{document.tags.map((tag) => (
							<span
								key={tag}
								className="rounded-full border border-cyan-500/30 bg-cyan-500/8 px-2.5 py-1 text-xs text-cyan-100/75"
							>
								#{tag}
							</span>
						))}
					</div>
				</section>
			) : null}
		</div>
	);
}
