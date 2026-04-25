"use client";

import { FolderOpen, Plus, Tag } from "lucide-react";

import { cn } from "@/lib/utils/cn";
import type { NoteFolder, NoteTag } from "@/types";

interface NoteSidebarProps {
	folders: NoteFolder[];
	tags: NoteTag[];
	selectedFolderId: number | null;
	selectedTagId: number | null;
	onSelectFolder: (folderId: number | null) => void;
	onSelectTag: (tagId: number | null) => void;
	onCreateFolder: () => void;
	onCreateTag: () => void;
}

export function NoteSidebar({
	folders,
	tags,
	selectedFolderId,
	selectedTagId,
	onSelectFolder,
	onSelectTag,
	onCreateFolder,
	onCreateTag,
}: NoteSidebarProps) {
	return (
		<aside className="space-y-6 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4 backdrop-blur">
			<section>
				<div className="mb-3 flex items-center justify-between">
					<p className="text-xs uppercase tracking-[0.2em] text-zinc-400">Folders</p>
					<button
						type="button"
						onClick={onCreateFolder}
						className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-300 transition hover:border-zinc-500"
					>
						<Plus className="h-3.5 w-3.5" />
						Add
					</button>
				</div>
				<div className="space-y-1">
					<button
						type="button"
						onClick={() => onSelectFolder(null)}
						className={cn(
							"flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition",
							selectedFolderId === null
								? "bg-zinc-800 text-zinc-100"
								: "text-zinc-300 hover:bg-zinc-800"
						)}
					>
						<FolderOpen className="h-4 w-4" />
						All Notes
					</button>
					{folders.map((folder) => (
						<button
							key={folder.id}
							type="button"
							onClick={() => onSelectFolder(folder.id)}
							className={cn(
								"flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition",
								selectedFolderId === folder.id
									? "bg-zinc-800 text-zinc-100"
									: "text-zinc-300 hover:bg-zinc-800"
							)}
						>
							<FolderOpen className="h-4 w-4" />
							{folder.name}
						</button>
					))}
				</div>
			</section>

			<section>
				<div className="mb-3 flex items-center justify-between">
					<p className="text-xs uppercase tracking-[0.2em] text-zinc-400">Tags</p>
					<button
						type="button"
						onClick={onCreateTag}
						className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-300 transition hover:border-zinc-500"
					>
						<Plus className="h-3.5 w-3.5" />
						Add
					</button>
				</div>
				<div className="flex flex-wrap gap-2">
					<button
						type="button"
						onClick={() => onSelectTag(null)}
						className={cn(
							"rounded-full border px-2.5 py-1 text-xs uppercase tracking-wider transition",
							selectedTagId === null
								? "border-zinc-500 bg-zinc-800 text-zinc-100"
								: "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500"
						)}
					>
						All
					</button>
					{tags.map((tag) => (
						<button
							key={tag.id}
							type="button"
							onClick={() => onSelectTag(tag.id)}
							className={cn(
								"inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs uppercase tracking-wider transition",
								selectedTagId === tag.id
									? "border-zinc-500 bg-zinc-800 text-zinc-100"
									: "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500"
							)}
						>
							<Tag className="h-3 w-3" />
							{tag.name}
						</button>
					))}
				</div>
			</section>
		</aside>
	);
}
