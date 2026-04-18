"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ChatHistory } from "@/components/features/chat/ChatHistory";
import { ChatInput } from "@/components/features/chat/ChatInput";
import { SaveAsNote } from "@/components/features/chat/SaveAsNote";
import { listFolders } from "@/lib/api/notes";
import { useChat } from "@/lib/hooks/useChat";
import type { NoteFolder } from "@/types";

export default function ChatSessionPage() {
	const params = useParams<{ sessionId: string }>();
	const [folders, setFolders] = useState<NoteFolder[]>([]);
	const [savedStatus, setSavedStatus] = useState<string | null>(null);

	const rawSessionId = Array.isArray(params.sessionId)
		? params.sessionId[0]
		: params.sessionId;
	const sessionId = Number(rawSessionId);

	const {
		selectedSession,
		renderedMessages,
		isLoading,
		isSendingMessage,
		isSavingAsNote,
		streamingMessageId,
		error,
		fetchSessionById,
		sendMessage,
		saveSessionAsNote,
		clearError,
	} = useChat();

	const activeSession = useMemo(() => {
		if (!selectedSession || selectedSession.id !== sessionId) {
			return null;
		}
		return selectedSession;
	}, [selectedSession, sessionId]);

	useEffect(() => {
		if (Number.isNaN(sessionId) || sessionId <= 0) {
			return;
		}

		void fetchSessionById(sessionId);
	}, [fetchSessionById, sessionId]);

	useEffect(() => {
		void listFolders()
			.then((response) => setFolders(response))
			.catch(() => setFolders([]));
	}, []);

	useEffect(() => {
		return () => {
			clearError();
		};
	}, [clearError]);

	if (Number.isNaN(sessionId) || sessionId <= 0) {
		return (
			<div className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-6 backdrop-blur">
				<p className="text-sm text-rose-300">Invalid session id.</p>
				<Link
					href="/dashboard/chat"
					className="inline-flex items-center gap-2 text-sm text-zinc-300 hover:text-zinc-100"
				>
					<ArrowLeft className="h-4 w-4" />
					Back to Sessions
				</Link>
			</div>
		);
	}

	return (
		<div className="space-y-4">
			<section className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-6 backdrop-blur">
				<div className="flex flex-wrap items-center justify-between gap-3">
					<div>
						<Link
							href="/dashboard/chat"
							className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-zinc-500 hover:text-zinc-300"
						>
							<ArrowLeft className="h-3.5 w-3.5" />
							All Sessions
						</Link>
						<h1 className="mt-2 text-2xl font-semibold text-zinc-100">
							{activeSession?.title || `Session ${sessionId}`}
						</h1>
						<p className="mt-1 text-sm text-zinc-400">
							{activeSession ? `${activeSession.messages.length} messages` : "Loading conversation..."}
						</p>
					</div>
				</div>
			</section>

			{error ? (
				<p className="rounded-lg border border-rose-900/50 bg-rose-950/30 p-3 text-sm text-rose-200">
					{error}
				</p>
			) : null}

			{savedStatus ? (
				<p className="rounded-lg border border-zinc-700 bg-zinc-900/70 p-3 text-sm text-zinc-200">
					{savedStatus}
				</p>
			) : null}

			<ChatHistory
				messages={activeSession ? renderedMessages : []}
				isLoading={isLoading}
				streamingMessageId={streamingMessageId}
			/>

			<ChatInput
				disabled={isSendingMessage || !activeSession}
				onSend={async (content) => {
					setSavedStatus(null);
					await sendMessage(sessionId, content);
				}}
			/>

			<SaveAsNote
				defaultTitle={activeSession?.title || `Session ${sessionId}`}
				folders={folders}
				isSaving={isSavingAsNote}
				onSave={async (payload) => {
					const note = await saveSessionAsNote(sessionId, payload);
					setSavedStatus(`Saved as note: \"${note.title}\"`);
				}}
			/>
		</div>
	);
}
