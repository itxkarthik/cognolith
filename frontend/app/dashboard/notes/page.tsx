"use client";

import { ChevronDown, ChevronRight, Clock3, FileText, FolderOpen, Tags } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { NoteEditor } from "@/components/features/notes/NoteEditor";
import { NoteSidebar } from "@/components/features/notes/NoteSidebar";
import { Separator } from "@/components/ui";
import { listNotes } from "@/lib/api/notes";
import { useAutoSave } from "@/lib/hooks/useAutoSave";
import { useNotes } from "@/lib/hooks/useNotes";
import {
  ensureMarkdown,
  extractMarkdownHeadings,
  extractWikiLinkTitles,
  markdownToPlainText,
} from "@/lib/markdown";
import type { NoteResponse } from "@/types";

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

type DraftState = {
  title: string;
  content: string;
  tagIds: number[];
};

const EMPTY_DRAFT: DraftState = {
  title: "",
  content: "",
  tagIds: [],
};

function draftFromNote(note: NoteResponse): DraftState {
  return {
    title: note.title,
    content: ensureMarkdown(note.content || "", note.content_type),
    tagIds: note.tag_ids ?? [],
  };
}

export default function NotesPage() {
  const {
    notes,
    total,
    selectedNote,
    folders,
    tags,
    filters,
    isLoading,
    isSaving,
    isDeleting,
    error,
    createNote,
    updateNoteById,
    deleteNoteById,
    createFolder,
    createTag,
    setSelectedNote,
    setSearch,
    setFolderFilter,
    setTagFilter,
    clearError,
    fetchNoteById,
  } = useNotes();

  const [draftsByNoteId, setDraftsByNoteId] = useState<Record<number, DraftState>>({});
  const [isCreatingNote, setIsCreatingNote] = useState(false);
  const [vaultNotes, setVaultNotes] = useState<NoteResponse[]>([]);
  const [isVaultLoading, setIsVaultLoading] = useState(false);
  const [requestedNoteId, setRequestedNoteId] = useState<number | null>(null);
  const handledNewNoteQueryRef = useRef(false);
  const deletingNoteIdsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("note");
    const noteId = value ? Number(value) : null;
    setRequestedNoteId(noteId && Number.isInteger(noteId) ? noteId : null);
  }, []);

  useEffect(() => {
    if (requestedNoteId === null || isLoading) return;

    setRequestedNoteId(null);
    void fetchNoteById(requestedNoteId);
  }, [fetchNoteById, isLoading, requestedNoteId]);

  const draft = useMemo(() => {
    if (!selectedNote) {
      return EMPTY_DRAFT;
    }

    return draftsByNoteId[selectedNote.id] ?? draftFromNote(selectedNote);
  }, [draftsByNoteId, selectedNote]);

  useEffect(() => {
    if (!selectedNote && notes.length > 0) {
      setSelectedNote(notes[0]);
    }
  }, [notes, selectedNote, setSelectedNote]);

  const refreshVaultNotes = useCallback(async () => {
    setIsVaultLoading(true);
    try {
      const response = await listNotes({
        search: filters.search || undefined,
        tag_id: filters.tagId ?? undefined,
        skip: 0,
        limit: 100,
      });
      setVaultNotes(response.data ?? []);
    } finally {
      setIsVaultLoading(false);
    }
  }, [filters.search, filters.tagId]);

  useEffect(() => {
    void refreshVaultNotes();
  }, [refreshVaultNotes]);

  useEffect(() => {
    if (notes.length === 0) return;

    setVaultNotes((current) => {
      const byId = new Map(current.map((note) => [note.id, note]));
      notes.forEach((note) => byId.set(note.id, note));
      return Array.from(byId.values());
    });
  }, [notes]);

  const setDraftForSelectedNote = useCallback(
    (updater: (prev: DraftState) => DraftState) => {
      if (!selectedNote) return;

      setDraftsByNoteId((prev) => {
        const current = prev[selectedNote.id] ?? draftFromNote(selectedNote);
        return {
          ...prev,
          [selectedNote.id]: updater(current),
        };
      });
    },
    [selectedNote]
  );

  const saveDraft = useCallback(
    async (value: DraftState) => {
      if (!selectedNote) return;
      if (deletingNoteIdsRef.current.has(selectedNote.id)) return;

      await updateNoteById(selectedNote.id, {
        title: value.title.trim() || "Untitled note",
        content: value.content.trim() || "Start writing...",
        content_type: "markdown",
        tag_ids: value.tagIds,
        folder_id: selectedNote.folder_id ?? null,
      });
    },
    [selectedNote, updateNoteById]
  );

  const { isSaving: isAutoSaving, lastSavedAt, error: autoSaveError } = useAutoSave({
    value: draft,
    onSave: saveDraft,
    enabled: Boolean(selectedNote),
    delayMs: 850,
    skipInitial: true,
  });

  const handleCreateNote = useCallback(async (folderId = filters.folderId) => {
    if (isCreatingNote) return;

    setIsCreatingNote(true);
    try {
      const created = await createNote({
        title: "Untitled note",
        content: "Start writing...",
        content_type: "markdown",
        folder_id: folderId,
        is_pinned: false,
        is_favorite: false,
        tag_ids: [],
      });
      setFolderFilter(folderId);
      setSelectedNote(created);
      await refreshVaultNotes();
    } finally {
      setIsCreatingNote(false);
    }
  }, [createNote, filters.folderId, isCreatingNote, refreshVaultNotes, setFolderFilter, setSelectedNote]);

  useEffect(() => {
    if (handledNewNoteQueryRef.current || isLoading || isCreatingNote) return;
    if (new URLSearchParams(window.location.search).get("new") !== "1") return;

    handledNewNoteQueryRef.current = true;
    window.history.replaceState({}, "", "/dashboard/notes");
    void handleCreateNote();
  }, [handleCreateNote, isCreatingNote, isLoading]);

  const handleCreateFolder = useCallback(
    async (parentFolderId?: number | null) => {
      const name = window.prompt(parentFolderId ? "Subfolder name" : "Folder name");
      if (!name?.trim()) return;

      const folder = await createFolder({ name: name.trim(), parent_folder_id: parentFolderId ?? null });
      setFolderFilter(folder.id);
    },
    [createFolder, setFolderFilter]
  );

  const handleDeleteSelected = useCallback(async () => {
    if (!selectedNote) return;

    const noteId = selectedNote.id;
    const confirmed = window.confirm(`Delete note \"${selectedNote.title}\"? This cannot be undone.`);
    if (!confirmed) return;

    deletingNoteIdsRef.current.add(noteId);
    setSelectedNote(null);
    setDraftsByNoteId((prev) => {
      const next = { ...prev };
      delete next[noteId];
      return next;
    });

    try {
      await deleteNoteById(noteId);
      setVaultNotes((current) => current.filter((note) => note.id !== noteId));
      clearError();
    } finally {
      deletingNoteIdsRef.current.delete(noteId);
    }
  }, [clearError, deleteNoteById, selectedNote, setSelectedNote]);

  const isSavingState = isSaving || isAutoSaving;
  const selectedFolderName = useMemo(() => {
    if (filters.folderId === null) {
      return "All notes";
    }

    return folders.find((folder) => folder.id === filters.folderId)?.name ?? "Folder";
  }, [filters.folderId, folders]);

  const treeNotes = vaultNotes.length > 0 ? vaultNotes : notes;
  const headings = useMemo(() => extractMarkdownHeadings(draft.content), [draft.content]);
  const previewText = useMemo(() => markdownToPlainText(draft.content), [draft.content]);
  const wikiLinkTitles = useMemo(() => extractWikiLinkTitles(draft.content), [draft.content]);
  const linkedNotes = useMemo(
    () =>
      wikiLinkTitles
        .map((title) => treeNotes.find((note) => note.title.toLocaleLowerCase() === title.toLocaleLowerCase()))
        .filter((note): note is NoteResponse => Boolean(note)),
    [treeNotes, wikiLinkTitles]
  );
  const backlinks = useMemo(
    () =>
      selectedNote
        ? treeNotes.filter(
            (note) => note.id !== selectedNote.id && note.linked_note_ids.includes(selectedNote.id)
          )
        : [],
    [selectedNote, treeNotes]
  );

  const selectLinkedNote = useCallback(
    (note: NoteResponse) => {
      setFolderFilter(note.folder_id ?? null);
      setSelectedNote(note);
    },
    [setFolderFilter, setSelectedNote]
  );

  const navigateToHeading = useCallback(
    (offset: number) => {
      window.dispatchEvent(new CustomEvent<number>("note-editor:navigate", { detail: offset }));
    },
    []
  );

  return (
    <div className="space-y-3">
      {error ? <p className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 p-3 text-sm text-[#a50011]">{error}</p> : null}

      <section className="overflow-hidden border border-border bg-background">
        <div className="flex min-h-[calc(100dvh-6.5rem)] flex-col xl:grid xl:grid-cols-[340px_minmax(0,1fr)_300px]">
        <NoteSidebar
          folders={folders}
          notes={treeNotes}
          tags={tags}
          selectedFolderId={filters.folderId}
          selectedNoteId={selectedNote?.id ?? null}
          selectedTagId={filters.tagId}
          search={filters.search}
          total={treeNotes.length || total}
          onSearchChange={setSearch}
          onSelectFolder={setFolderFilter}
          onSelectNote={(note) => {
            setFolderFilter(note.folder_id ?? null);
            setSelectedNote(note);
          }}
          onSelectTag={setTagFilter}
          onCreateFolder={(parentFolderId) => {
            void handleCreateFolder(parentFolderId);
          }}
          onCreateNote={(folderId) => {
            void handleCreateNote(folderId ?? null);
          }}
          onCreateTag={() => {
            const name = window.prompt("Tag name");
            if (!name?.trim()) return;
            void createTag({ name: name.trim(), color: "#a1a1aa" });
          }}
        />

        <div className="relative min-h-0 border-r border-border bg-background">
          {(isLoading || isVaultLoading || isCreatingNote) && !selectedNote ? (
            <div className="absolute inset-x-0 top-0 z-10 border-b border-border bg-muted px-4 py-2 text-xs text-muted-foreground">
              Loading vault...
            </div>
          ) : null}

          <NoteEditor
            note={selectedNote}
            title={draft.title}
            content={draft.content}
            selectedTagIds={draft.tagIds}
            tags={tags}
            isSaving={isSavingState}
            lastSavedAt={lastSavedAt}
            autoSaveError={autoSaveError}
            onTitleChange={(title) => {
              setDraftForSelectedNote((prev) => ({ ...prev, title }));
            }}
            onContentChange={(content) => {
              setDraftForSelectedNote((prev) => ({ ...prev, content }));
            }}
            onToggleTag={(tagId) => {
              setDraftForSelectedNote((prev) => {
                const exists = prev.tagIds.includes(tagId);
                return {
                  ...prev,
                  tagIds: exists ? prev.tagIds.filter((id) => id !== tagId) : [...prev.tagIds, tagId],
                };
              });
            }}
            onDelete={handleDeleteSelected}
            isDeleting={isDeleting}
            className="min-h-0 border-0 xl:flex xl:h-full xl:flex-col"
          />
        </div>

        <aside className="min-h-0 border-t border-border bg-background xl:border-l xl:border-t-0">
          <div className="border-b border-border p-3">
            <p className="text-xs text-muted-foreground">OUTLINE</p>
            <h2 className="mt-1 line-clamp-1 text-sm font-bold text-foreground">{selectedNote?.title ?? "No note selected"}</h2>
          </div>

          <div className="space-y-4 p-3">
            <section className="space-y-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-2 text-foreground">
                <FolderOpen className="h-3.5 w-3.5" />
                <span>{selectedFolderName}</span>
              </div>
              {selectedNote ? (
                <>
                  <div className="flex items-center gap-2">
                    <Clock3 className="h-3.5 w-3.5" />
                    <span>Updated {formatDateTime(selectedNote.updated_at)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Tags className="h-3.5 w-3.5" />
                    <span>{draft.tagIds.length} {draft.tagIds.length === 1 ? "tag" : "tags"}</span>
                  </div>
                </>
              ) : null}
            </section>

            <Separator />

            <section>
              <p className="mb-2 text-xs text-muted-foreground">HEADINGS</p>
              {headings.length > 0 ? (
                <nav className="space-y-1">
                  {headings.map((heading) => (
                    <button
                      key={heading.id}
                      type="button"
                      onClick={() => navigateToHeading(heading.offset)}
                      className="flex w-full items-center gap-1 truncate border-l border-border py-1 pr-2 text-left text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                      style={{ paddingLeft: `${(heading.level - 1) * 14 + 8}px` }}
                      title={heading.title}
                    >
                      {heading.level === 1 ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
                      <span className="truncate">{heading.title}</span>
                    </button>
                  ))}
                </nav>
              ) : (
                <p className="border border-border bg-muted p-3 text-xs text-muted-foreground">
                  Add headings to build note navigation.
                </p>
              )}
            </section>

            <Separator />

            <section>
              <p className="mb-2 text-xs text-muted-foreground">LINKS</p>
              <div className="space-y-1 text-xs text-muted-foreground">
                {wikiLinkTitles.length > 0 ? wikiLinkTitles.map((title) => {
                  const linkedNote = linkedNotes.find(
                    (note) => note.title.toLocaleLowerCase() === title.toLocaleLowerCase()
                  );
                  return linkedNote ? (
                    <button
                      key={title}
                      type="button"
                      onClick={() => selectLinkedNote(linkedNote)}
                      className="flex w-full items-center gap-2 border-l border-border px-2 py-1 text-left hover:bg-muted hover:text-foreground"
                    >
                      <FileText className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{linkedNote.title}</span>
                    </button>
                  ) : (
                    <div key={title} className="flex items-center gap-2 border-l border-border px-2 py-1 opacity-60">
                      <FileText className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{title}</span>
                    </div>
                  );
                }) : (
                  <div className="flex items-center gap-2 border-l border-border px-2 py-1">
                    <FileText className="h-3.5 w-3.5" />
                    <span>No outgoing links</span>
                  </div>
                )}
                <div className="flex items-center gap-2 border-l border-border px-2 py-1">
                  <FileText className="h-3.5 w-3.5" />
                  <span>{previewText ? `${previewText.split(/\s+/).length} words` : "Empty note"}</span>
                </div>
              </div>
            </section>

            <Separator />

            <section>
              <p className="mb-2 text-xs text-muted-foreground">BACKLINKS</p>
              <div className="space-y-1 text-xs text-muted-foreground">
                {backlinks.length > 0 ? backlinks.map((note) => (
                  <button
                    key={note.id}
                    type="button"
                    onClick={() => selectLinkedNote(note)}
                    className="flex w-full items-center gap-2 border-l border-border px-2 py-1 text-left hover:bg-muted hover:text-foreground"
                  >
                    <FileText className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{note.title}</span>
                  </button>
                )) : (
                  <p className="border-l border-border px-2 py-1">No backlinks</p>
                )}
              </div>
            </section>
          </div>
        </aside>
      </div>
      </section>
    </div>
  );
}
