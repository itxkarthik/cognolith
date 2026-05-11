"use client";

import { Clock3, FileText } from "lucide-react";

import { formatDate, getStatusClasses } from "@/components/features/documents/utils";
import { cn } from "@/lib/utils/cn";
import type { DocumentContentResponse } from "@/types";

interface DocumentFullTextProps {
	document: DocumentContentResponse;
}

export function DocumentFullText({ document }: DocumentFullTextProps) {
	return (
		<div className="space-y-6">
			<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6">
				<div className="flex flex-wrap items-start justify-between gap-4">
					<div>
						<p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-cyan-300/55">
							<FileText className="h-3.5 w-3.5" />
							Full Text View
						</p>
						<h1 className="mt-2 text-3xl font-semibold text-cyan-50">{document.title}</h1>
						<p className="mt-2 inline-flex items-center gap-1.5 text-sm text-cyan-100/65">
							<Clock3 className="h-4 w-4" />
							Updated {formatDate(document.updated_at)}
						</p>
					</div>

					<span
						className={cn(
							"rounded-full border px-2 py-1 text-xs font-medium capitalize",
							getStatusClasses(document.status)
						)}
					>
						{document.status}
					</span>
				</div>
			</section>

			<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6">
				<h2 className="text-lg font-semibold text-cyan-50">Document Content</h2>
				{document.content ? (
					<pre className="mt-4 max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-xl border border-cyan-500/20 bg-[#01040f] p-4 text-sm leading-6 text-cyan-100/80">
						{document.content}
					</pre>
				) : (
					<p className="mt-3 text-sm text-cyan-100/60">
						Full text content is not available yet for this document.
					</p>
				)}
			</section>
		</div>
	);
}
