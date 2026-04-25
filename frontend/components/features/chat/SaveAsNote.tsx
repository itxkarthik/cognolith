"use client";

import { CheckCircle2, Loader2, NotebookPen } from "lucide-react";
import { useState } from "react";

import type { NoteFolder } from "@/types";

interface SaveAsNotePayload {
	title?: string | null;
	folder_id?: number | null;
}

interface SaveAsNoteProps {
	defaultTitle?: string | null;
	folders: NoteFolder[];
	isSaving: boolean;
	onSave: (payload: SaveAsNotePayload) => Promise<void>;
}

export function SaveAsNote({
	defaultTitle,
	folders,
	isSaving,
	onSave,
}: SaveAsNoteProps) {
	const [isOpen, setIsOpen] = useState(false);
	const [title, setTitle] = useState("");
	const [hasEditedTitle, setHasEditedTitle] = useState(false);
	const [folderId, setFolderId] = useState<string>("");
	const [statusMessage, setStatusMessage] = useState<string | null>(null);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);

	const effectiveTitle = hasEditedTitle ? title : defaultTitle ?? "";

	return (
		<section className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3 backdrop-blur">
			<div className="flex items-center justify-between gap-2">
				<div>
					<p className="text-xs uppercase tracking-[0.16em] text-zinc-500">Utilities</p>
					<p className="mt-1 text-sm text-zinc-300">Save this conversation as a note</p>
				</div>
				<button
					type="button"
					onClick={() => setIsOpen((current) => !current)}
					className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 transition hover:border-zinc-500"
				>
					<NotebookPen className="h-3.5 w-3.5" />
					Save as Note
				</button>
			</div>

			{isOpen ? (
				<form
					onSubmit={(event) => {
						event.preventDefault();
						setStatusMessage(null);
						setErrorMessage(null);

						void onSave({
							title: effectiveTitle.trim() || undefined,
							folder_id: folderId ? Number(folderId) : undefined,
						})
							.then(() => {
								setStatusMessage("Conversation saved to notes.");
							})
							.catch((error) => {
								setErrorMessage(
									error instanceof Error ? error.message : "Failed to save chat as note."
								);
							});
					}}
					className="mt-3 space-y-2"
				>
					<input
						type="text"
						value={effectiveTitle}
						onChange={(event) => {
							setHasEditedTitle(true);
							setTitle(event.target.value);
						}}
						placeholder="Note title"
						className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-500 focus:outline-none"
					/>

					<select
						value={folderId}
						onChange={(event) => setFolderId(event.target.value)}
						className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-zinc-500 focus:outline-none"
					>
						<option value="">No folder</option>
						{folders.map((folder) => (
							<option key={folder.id} value={folder.id}>
								{folder.name}
							</option>
						))}
					</select>

					<button
						type="submit"
						disabled={isSaving}
						className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-100 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-60"
					>
						{isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <NotebookPen className="h-3.5 w-3.5" />}
						Save Conversation
					</button>

					{statusMessage ? (
						<p className="flex items-center gap-1.5 text-xs text-zinc-300">
							<CheckCircle2 className="h-3.5 w-3.5" />
							{statusMessage}
						</p>
					) : null}

					{errorMessage ? <p className="text-xs text-rose-300">{errorMessage}</p> : null}
				</form>
			) : null}
		</section>
	);
}
