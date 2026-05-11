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
		<aside className="space-y-6 rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-4 backdrop-blur">
			<section>
				<div className="mb-3 flex items-center justify-between">
					<p className="text-xs uppercase tracking-[0.2em] text-cyan-300/60">Folders</p>
					<button
						type="button"
						onClick={onCreateFolder}
						className="inline-flex items-center gap-1 rounded-md border border-cyan-500/30 px-2 py-1 text-xs text-cyan-100/80 transition hover:border-cyan-400/50"
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
								? "bg-cyan-500/20 text-cyan-100"
								: "text-cyan-100/75 hover:bg-cyan-500/12"
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
									? "bg-cyan-500/20 text-cyan-100"
									: "text-cyan-100/75 hover:bg-cyan-500/12"
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
					<p className="text-xs uppercase tracking-[0.2em] text-cyan-300/60">Tags</p>
					<button
						type="button"
						onClick={onCreateTag}
						className="inline-flex items-center gap-1 rounded-md border border-cyan-500/30 px-2 py-1 text-xs text-cyan-100/80 transition hover:border-cyan-400/50"
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
								? "border-cyan-400/50 bg-cyan-500/18 text-cyan-100"
								: "border-cyan-500/30 bg-cyan-500/8 text-cyan-100/65 hover:border-cyan-400/50"
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
									? "border-cyan-400/50 bg-cyan-500/18 text-cyan-100"
									: "border-cyan-500/30 bg-cyan-500/8 text-cyan-100/65 hover:border-cyan-400/50"
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
