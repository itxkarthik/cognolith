"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api/client";
import type {
	DocumentList,
	DocumentResponse,
	NoteList,
	NoteResponse,
} from "@/types";

interface UseDashboardOverviewResult {
	notes: NoteResponse[];
	documents: DocumentResponse[];
	noteCount: number;
	documentCount: number;
	isLoading: boolean;
	errorMessage: string | null;
}

export function useDashboardOverview(): UseDashboardOverviewResult {
	const [notes, setNotes] = useState<NoteResponse[]>([]);
	const [documents, setDocuments] = useState<DocumentResponse[]>([]);
	const [noteCount, setNoteCount] = useState(0);
	const [documentCount, setDocumentCount] = useState(0);
	const [isLoading, setIsLoading] = useState(true);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);

	useEffect(() => {
		let active = true;

		const loadOverviewData = async () => {
			setIsLoading(true);
			setErrorMessage(null);

			try {
				const [notesResponse, documentsResponse] = await Promise.all([
					apiClient.get<NoteList>("/notes", {
						params: { skip: 0, limit: 5 },
					}),
					apiClient.get<DocumentList>("/documents", {
						params: { skip: 0, limit: 5 },
					}),
				]);

				if (!active) {
					return;
				}

				setNotes(notesResponse.data.data ?? []);
				setDocuments(documentsResponse.data.data ?? []);
				setNoteCount(notesResponse.data.count ?? 0);
				setDocumentCount(documentsResponse.data.count ?? 0);
			} catch (error) {
				if (!active) {
					return;
				}

				setErrorMessage(
					error instanceof Error
						? error.message
						: "Failed to load dashboard overview."
				);
			} finally {
				if (active) {
					setIsLoading(false);
				}
			}
		};

		void loadOverviewData();

		return () => {
			active = false;
		};
	}, []);

	return {
		notes,
		documents,
		noteCount,
		documentCount,
		isLoading,
		errorMessage,
	};
}
