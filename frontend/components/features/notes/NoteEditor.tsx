"use client";

import { Clock3, Save, Trash2 } from "lucide-react";

import { TipTapEditor } from "@/components/editors/TipTapEditor";
import { cn } from "@/lib/utils/cn";
import type { NoteResponse, NoteTag } from "@/types";

interface NoteEditorProps {
	note: NoteResponse | null;
	title: string;
	content: string;
	selectedTagIds: number[];
	tags: NoteTag[];
	isSaving: boolean;
	lastSavedAt: Date | null;
	autoSaveError: string | null;
	onTitleChange: (title: string) => void;
	onContentChange: (content: string) => void;
	onToggleTag: (tagId: number) => void;
	onDelete: () => Promise<void>;
	isDeleting?: boolean;
}

export function NoteEditor({
	note,
	title,
	content,
	selectedTagIds,
	tags,
	isSaving,
	lastSavedAt,
	autoSaveError,
	onTitleChange,
	onContentChange,
	onToggleTag,
	onDelete,
	isDeleting = false,
}: NoteEditorProps) {
	if (!note) {
		return (
			<div className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6 text-cyan-100/70 backdrop-blur">
				<p className="text-sm uppercase tracking-[0.16em] text-cyan-300/55">Editor</p>
				<h2 className="mt-2 text-lg font-semibold text-cyan-50">No note selected</h2>
				<p className="mt-2 text-sm text-cyan-100/60">
					Pick a note from the list or create one from a template.
				</p>
			</div>
		);
	}

	return (
		<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-4 backdrop-blur">
			<div className="mb-3 flex flex-wrap items-start justify-between gap-3">
				<div className="min-w-0 flex-1">
					<p className="text-xs uppercase tracking-[0.2em] text-cyan-300/55">Entry Editor</p>
					<input
						type="text"
						value={title}
						onChange={(event) => onTitleChange(event.target.value)}
						placeholder="Untitled note"
						className="mt-2 w-full rounded-lg border border-cyan-500/30 bg-cyan-500/5 px-3 py-2 text-xl font-semibold text-cyan-50 placeholder:text-cyan-300/45 focus:border-cyan-400/60 focus:outline-none"
					/>
				</div>

				<div className="flex items-center gap-2">
					<button
						type="button"
						onClick={() => {
							void onDelete();
						}}
						disabled={isDeleting}
						className="inline-flex items-center gap-2 rounded-lg border border-rose-700/65 px-3 py-2 text-sm text-rose-200 transition hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-50"
					>
						<Trash2 className="h-4 w-4" />
						{isDeleting ? "Deleting..." : "Delete"}
					</button>
				</div>
			</div>

			<div className="mb-3 flex flex-wrap items-center gap-2">
				{tags.map((tag) => {
					const active = selectedTagIds.includes(tag.id);
					return (
						<button
							key={tag.id}
							type="button"
							onClick={() => onToggleTag(tag.id)}
							className={cn(
								"rounded-full border px-2.5 py-1 text-xs uppercase tracking-wider transition",
								active
									? "border-cyan-400/55 bg-cyan-500/20 text-cyan-100"
									: "border-cyan-500/28 bg-cyan-500/7 text-cyan-100/65 hover:border-cyan-400/50"
							)}
						>
							#{tag.name}
						</button>
					);
				})}
			</div>

			<TipTapEditor value={content} onChange={onContentChange} />

			<div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-cyan-100/60">
				<div className="inline-flex items-center gap-2">
					{isSaving ? (
						<>
							<Save className="h-3.5 w-3.5" />
							Saving...
						</>
					) : lastSavedAt ? (
						<>
							<Clock3 className="h-3.5 w-3.5" />
							Saved {lastSavedAt.toLocaleTimeString()}
						</>
					) : (
						"No changes saved yet"
					)}
				</div>
				{autoSaveError ? (
					<span className="text-rose-300">{autoSaveError}</span>
				) : (
					<span>FORMAT: HTML · MODE: AUTOSAVE</span>
				)}
			</div>
		</section>
	);
}
