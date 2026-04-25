"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

import { DocumentViewer } from "@/components/features/documents";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { useDocumentStore } from "@/store/documentStore";

export default function DocumentDetailsPage() {
	const params = useParams<{ id: string }>();
	const router = useRouter();

	const selectedDocument = useDocumentStore((state) => state.selectedDocument);
	const isLoading = useDocumentStore((state) => state.isLoading);
	const isDeleting = useDocumentStore((state) => state.isDeleting);
	const error = useDocumentStore((state) => state.error);
	const fetchDocumentById = useDocumentStore((state) => state.fetchDocumentById);
	const clearSelectedDocument = useDocumentStore(
		(state) => state.clearSelectedDocument
	);
	const deleteDocumentById = useDocumentStore((state) => state.deleteDocumentById);

	const documentId = Number(params.id);
	const isValidId = Number.isInteger(documentId) && documentId > 0;

	useEffect(() => {
		if (!isValidId) {
			return;
		}

		void fetchDocumentById(documentId);

		return () => {
			clearSelectedDocument();
		};
	}, [clearSelectedDocument, documentId, fetchDocumentById, isValidId]);

	return (
		<div className="space-y-6">
			<Link
				href="/dashboard/documents"
				className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-100 transition hover:border-zinc-500"
			>
				<ArrowLeft className="h-4 w-4" />
				Back to Documents
			</Link>

			{!isValidId ? (
				<p className="rounded-xl border border-rose-800/60 bg-rose-950/30 p-4 text-sm text-rose-200">
					Invalid document id.
				</p>
			) : isLoading && !selectedDocument ? (
				<div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-6">
					<LoadingSpinner label="Loading document..." />
				</div>
			) : error ? (
				<p className="rounded-xl border border-rose-800/60 bg-rose-950/30 p-4 text-sm text-rose-200">
					{error}
				</p>
			) : selectedDocument ? (
				<DocumentViewer
					document={selectedDocument}
					isDeleting={isDeleting}
					onDelete={async (id) => {
						await deleteDocumentById(id);
						router.replace("/dashboard/documents");
					}}
				/>
			) : (
				<p className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4 text-sm text-zinc-300">
					Document not found.
				</p>
			)}
		</div>
	);
}
