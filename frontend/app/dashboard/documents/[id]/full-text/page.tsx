"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { DocumentFullText } from "@/components/features/documents";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { getDocumentContent } from "@/lib/api/documents";
import type { DocumentContentResponse } from "@/types";

export default function DocumentFullTextPage() {
	const params = useParams<{ id: string }>();
	const [document, setDocument] = useState<DocumentContentResponse | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);

	const documentId = Number(params.id);
	const isValidId = Number.isInteger(documentId) && documentId > 0;

	useEffect(() => {
		if (!isValidId) {
			setIsLoading(false);
			setErrorMessage("Invalid document id.");
			return;
		}

		let active = true;

		const loadDocumentContent = async () => {
			setIsLoading(true);
			setErrorMessage(null);
			try {
				const response = await getDocumentContent(documentId);
				if (!active) {
					return;
				}
				setDocument(response);
			} catch (error) {
				if (!active) {
					return;
				}
				setErrorMessage(
					error instanceof Error
						? error.message
						: "Failed to load document content."
				);
			} finally {
				if (active) {
					setIsLoading(false);
				}
			}
		};

		void loadDocumentContent();

		return () => {
			active = false;
		};
	}, [documentId, isValidId]);

	return (
		<div className="space-y-6">
			<Link
				href={`/dashboard/documents/${params.id}`}
				className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-100 transition hover:border-zinc-500"
			>
				<ArrowLeft className="h-4 w-4" />
				Back to Document Details
			</Link>

			{isLoading ? (
				<div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-6">
					<LoadingSpinner label="Loading full document text..." />
				</div>
			) : errorMessage ? (
				<p className="rounded-xl border border-rose-800/60 bg-rose-950/30 p-4 text-sm text-rose-200">
					{errorMessage}
				</p>
			) : document ? (
				<DocumentFullText document={document} />
			) : (
				<p className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4 text-sm text-zinc-300">
					Document content not found.
				</p>
			)}
		</div>
	);
}
