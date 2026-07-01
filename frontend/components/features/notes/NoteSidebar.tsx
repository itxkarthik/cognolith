"use client";

import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, FolderPlus, Plus, Search, Tag } from "lucide-react";
import { useMemo, useState } from "react";

import { Button, Input } from "@/components/ui";
import { cn } from "@/lib/utils/cn";
import type { NoteFolder, NoteResponse, NoteTag } from "@/types";

interface NoteSidebarProps {
  folders: NoteFolder[];
  notes: NoteResponse[];
  tags: NoteTag[];
  selectedFolderId: number | null;
  selectedNoteId: number | null;
  selectedTagId: number | null;
  search: string;
  total: number;
  onSearchChange: (search: string) => void;
  onSelectFolder: (folderId: number | null) => void;
  onSelectNote: (note: NoteResponse) => void;
  onSelectTag: (tagId: number | null) => void;
  onCreateFolder: (parentFolderId?: number | null) => void;
  onCreateNote: (folderId?: number | null) => void;
  onCreateTag: () => void;
}

function sortByName<T extends { name: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => a.name.localeCompare(b.name));
}

function sortNotes(notes: NoteResponse[]): NoteResponse[] {
  return [...notes].sort((a, b) => a.title.localeCompare(b.title));
}

export function NoteSidebar({
  folders,
  notes,
  tags,
  selectedFolderId,
  selectedNoteId,
  selectedTagId,
  search,
  total,
  onSearchChange,
  onSelectFolder,
  onSelectNote,
  onSelectTag,
  onCreateFolder,
  onCreateNote,
  onCreateTag,
}: NoteSidebarProps) {
  const [collapsedFolderIds, setCollapsedFolderIds] = useState<Set<number>>(() => new Set());
  const [isRootExpanded, setIsRootExpanded] = useState(true);

  const foldersByParent = useMemo(() => {
    return folders.reduce<Record<string, NoteFolder[]>>((acc, folder) => {
      const key = String(folder.parent_folder_id ?? "root");
      acc[key] = [...(acc[key] ?? []), folder];
      return acc;
    }, {});
  }, [folders]);

  const notesByFolder = useMemo(() => {
    return notes.reduce<Record<string, NoteResponse[]>>((acc, note) => {
      const key = String(note.folder_id ?? "root");
      acc[key] = [...(acc[key] ?? []), note];
      return acc;
    }, {});
  }, [notes]);

  const toggleFolder = (folderId: number) => {
    setCollapsedFolderIds((current) => {
      const next = new Set(current);
      if (next.has(folderId)) {
        next.delete(folderId);
      } else {
        next.add(folderId);
      }
      return next;
    });
  };

  const renderNote = (note: NoteResponse, depth: number) => {
    const active = selectedNoteId === note.id;

    return (
      <button
        key={note.id}
        type="button"
        onClick={() => onSelectNote(note)}
        className={cn(
          "flex h-8 w-full items-center gap-2 px-2 text-left text-sm transition",
          active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
        )}
        style={{ paddingLeft: `${depth * 14 + 12}px` }}
        title={note.title}
      >
        <FileText className="h-4 w-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{note.title || "Untitled note"}</span>
      </button>
    );
  };

  const renderFolder = (folder: NoteFolder, depth: number) => {
    const childFolders = sortByName(foldersByParent[String(folder.id)] ?? []);
    const childNotes = sortNotes(notesByFolder[String(folder.id)] ?? []);
    const expanded = !collapsedFolderIds.has(folder.id);
    const active = selectedFolderId === folder.id && selectedNoteId === null;

    return (
      <div key={folder.id}>
        <div
          className={cn(
            "group/folder flex h-8 items-center gap-1 pr-1 text-sm transition",
            active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
          style={{ paddingLeft: `${depth * 14 + 4}px` }}
        >
          <button
            type="button"
            onClick={() => toggleFolder(folder.id)}
            className="inline-flex h-7 w-5 shrink-0 items-center justify-center text-muted-foreground hover:text-foreground"
            aria-label={expanded ? `Collapse ${folder.name}` : `Expand ${folder.name}`}
          >
            {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={() => onSelectFolder(folder.id)}
            className="flex min-w-0 flex-1 items-center gap-2 text-left"
            title={folder.name}
          >
            {expanded ? <FolderOpen className="h-4 w-4 shrink-0" /> : <Folder className="h-4 w-4 shrink-0" />}
            <span className="truncate">{folder.name}</span>
          </button>
          <button
            type="button"
            onClick={() => onCreateNote(folder.id)}
            className="hidden h-6 w-6 shrink-0 items-center justify-center border border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground group-hover/folder:inline-flex"
            aria-label={`Create note in ${folder.name}`}
            title="New note"
          >
            <Plus className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={() => onCreateFolder(folder.id)}
            className="hidden h-6 w-6 shrink-0 items-center justify-center border border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground group-hover/folder:inline-flex"
            aria-label={`Create subfolder in ${folder.name}`}
            title="New subfolder"
          >
            <FolderPlus className="h-3 w-3" />
          </button>
        </div>

        {expanded ? (
          <div>
            {childFolders.map((child) => renderFolder(child, depth + 1))}
            {childNotes.map((note) => renderNote(note, depth + 1))}
          </div>
        ) : null}
      </div>
    );
  };

  const rootFolders = sortByName(foldersByParent.root ?? []);
  const rootNotes = sortNotes(notesByFolder.root ?? []);

  return (
    <aside className="min-h-0 border-r border-border bg-background">
      <section className="flex h-full min-h-0 flex-col">
        <div className="border-b border-border p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground">VAULT</p>
              <p className="mt-1 text-[10px] text-muted-foreground">{total} {total === 1 ? "file" : "files"}</p>
            </div>
            <div className="flex items-center gap-1">
              <Button type="button" size="icon-xs" variant="outline" onClick={() => onCreateNote(selectedFolderId)} aria-label="Create note" title="New note">
                <Plus className="h-3.5 w-3.5" />
              </Button>
              <Button type="button" size="icon-xs" variant="outline" onClick={() => onCreateFolder(selectedFolderId)} aria-label="Create folder" title="New folder">
                <FolderPlus className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          <div className="relative mt-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input type="search" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search vault" className="h-9 pl-9" />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          <div>
            <div
              className={cn(
                "group/root flex h-8 items-center gap-1 pr-1 text-sm transition",
                selectedFolderId === null && selectedNoteId === null ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <button
                type="button"
                onClick={() => setIsRootExpanded((current) => !current)}
                className="inline-flex h-7 w-5 shrink-0 items-center justify-center text-muted-foreground hover:text-foreground"
                aria-label={isRootExpanded ? "Collapse all notes" : "Expand all notes"}
              >
                {isRootExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              </button>
              <button type="button" onClick={() => onSelectFolder(null)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                {isRootExpanded ? <FolderOpen className="h-4 w-4 shrink-0" /> : <Folder className="h-4 w-4 shrink-0" />}
                <span className="truncate">All notes</span>
              </button>
              <button
                type="button"
                onClick={() => onCreateNote(null)}
                className="hidden h-6 w-6 shrink-0 items-center justify-center border border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground group-hover/root:inline-flex"
                aria-label="Create unfiled note"
                title="New note"
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>

            {isRootExpanded ? (
              <div>
                {rootFolders.map((folder) => renderFolder(folder, 1))}
                {rootNotes.map((note) => renderNote(note, 1))}
              </div>
            ) : null}
          </div>
        </div>

        <section className="border-t border-border">
          <div className="flex h-10 items-center justify-between border-b border-border px-3">
            <p className="text-xs font-medium text-muted-foreground">TAGS</p>
            <Button type="button" onClick={onCreateTag} size="icon-xs" variant="outline" aria-label="Create tag" title="New tag">
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
          <div className="flex max-h-32 flex-wrap gap-2 overflow-y-auto p-3">
            <button
              type="button"
              onClick={() => onSelectTag(null)}
              className={cn(
                "rounded-sm border px-2.5 py-1 text-xs transition",
                selectedTagId === null ? "border-border bg-accent text-foreground" : "border-border bg-muted text-muted-foreground hover:bg-accent"
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
                  "inline-flex items-center gap-1 rounded-sm border px-2.5 py-1 text-xs transition",
                  selectedTagId === tag.id ? "border-border bg-accent text-foreground" : "border-border bg-muted text-muted-foreground hover:bg-accent"
                )}
              >
                <Tag className="h-3 w-3" />
                {tag.name}
              </button>
            ))}
          </div>
        </section>
      </section>
    </aside>
  );
}
