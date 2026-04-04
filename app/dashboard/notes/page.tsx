"use client";

import { Grid2X2, List, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { NoteEditor } from "@/components/features/notes/NoteEditor";
import {
  getDefaultNoteTemplates,
  NoteTemplates,
} from "@/components/features/notes/NoteTemplates";
import { NoteSidebar } from "@/components/features/notes/NoteSidebar";
import { useAutoSave } from "@/lib/hooks/useAutoSave";
import { useNotes } from "@/lib/hooks/useNotes";

function stripHtmlTags(content: string): string {
  return content.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

type DraftState = {
  title: string;
  content: string;
  tagIds: number[];
};

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
    setViewMode,
  } = useNotes();

  const [draft, setDraft] = useState<DraftState>({
    title: "",
    content: "<p></p>",
    tagIds: [],
  });

  useEffect(() => {
    if (!selectedNote) {
      return;
    }

    setDraft({
      title: selectedNote.title,
      content: selectedNote.content || "<p></p>",
      tagIds: selectedNote.tag_ids ?? [],
    });
  }, [selectedNote]);

  useEffect(() => {
    if (!selectedNote && notes.length > 0) {
      setSelectedNote(notes[0]);
    }
  }, [notes, selectedNote, setSelectedNote]);

  const saveDraft = useCallback(
    async (value: DraftState) => {
      if (!selectedNote) {
        return;
      }

      await updateNoteById(selectedNote.id, {
        title: value.title.trim() || "Untitled note",
        content: value.content || "<p></p>",
        content_type: "html",
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

  const templates = useMemo(() => getDefaultNoteTemplates(), []);

  const handleCreateNote = useCallback(async () => {
    const created = await createNote({
      title: "Untitled note",
      content: "<p>Start writing...</p>",
      content_type: "html",
      folder_id: filters.folderId,
      is_pinned: false,
      is_favorite: false,
      tag_ids: [],
    });
    setSelectedNote(created);
  }, [createNote, filters.folderId, setSelectedNote]);

  const handleCreateFromTemplate = useCallback(
    async (template: { name: string; content: string; tags: string[] }) => {
      const templateTagIds = tags
        .filter((tag) => template.tags.some((templateTag) => templateTag === tag.name))
        .map((tag) => tag.id);

      const created = await createNote({
        title: template.name,
        content: template.content,
        content_type: "html",
        folder_id: filters.folderId,
        tag_ids: templateTagIds,
        is_pinned: false,
        is_favorite: false,
      });
      setSelectedNote(created);
    },
    [createNote, filters.folderId, setSelectedNote, tags]
  );

  const handleDeleteSelected = useCallback(async () => {
    if (!selectedNote) {
      return;
    }

    const confirmed = window.confirm(
      `Delete note \"${selectedNote.title}\"? This cannot be undone.`
    );
    if (!confirmed) {
      return;
    }

    await deleteNoteById(selectedNote.id);
  }, [deleteNoteById, selectedNote]);

  const isSavingState = isSaving || isAutoSaving;

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-zinc-500">Obsidian Engine</p>
            <h1 className="mt-2 text-2xl font-semibold text-[#dee5ff]">Notes</h1>
            <p className="mt-1 text-sm text-zinc-400">
              High-signal capture surface for research, meetings, and memory.
            </p>
            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
              {total} {total === 1 ? "entry" : "entries"} indexed
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => {
                void handleCreateNote();
              }}
              className="inline-flex items-center gap-2 rounded-lg border border-[#40485d] bg-[#141f38] px-3 py-2 text-sm text-zinc-100 transition hover:border-[#94aaff]/40"
            >
              <Plus className="h-4 w-4" />
              New Note
            </button>
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border transition ${
                filters.viewMode === "grid"
                  ? "border-[#94aaff]/40 bg-[#94aaff]/10 text-[#c7d4ff]"
                  : "border-zinc-700 text-zinc-300 hover:border-zinc-500"
              }`}
            >
              <Grid2X2 className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border transition ${
                filters.viewMode === "list"
                  ? "border-[#94aaff]/40 bg-[#94aaff]/10 text-[#c7d4ff]"
                  : "border-zinc-700 text-zinc-300 hover:border-zinc-500"
              }`}
            >
              <List className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="relative mt-4 max-w-xl">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            type="search"
            value={filters.search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search title or content"
            className="w-full rounded-lg border border-zinc-700 bg-[#091328] py-2 pl-9 pr-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-[#94aaff]/50 focus:outline-none"
          />
        </div>
      </section>

      <NoteTemplates onUseTemplate={handleCreateFromTemplate} templates={templates} />

      {error ? (
        <p className="rounded-lg border border-rose-900/50 bg-rose-950/30 p-3 text-sm text-rose-200">
          {error}
        </p>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[280px_360px_minmax(0,1fr)]">
        <NoteSidebar
          folders={folders}
          tags={tags}
          selectedFolderId={filters.folderId}
          selectedTagId={filters.tagId}
          onSelectFolder={setFolderFilter}
          onSelectTag={setTagFilter}
          onCreateFolder={() => {
            const name = window.prompt("Folder name");
            if (!name?.trim()) {
              return;
            }
            void createFolder({ name: name.trim() });
          }}
          onCreateTag={() => {
            const name = window.prompt("Tag name");
            if (!name?.trim()) {
              return;
            }
            void createTag({ name: name.trim(), color: "#94aaff" });
          }}
        />

        <section className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-3">
          <p className="mb-2 text-xs uppercase tracking-[0.2em] text-zinc-500">Entries</p>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 7 }).map((_, index) => (
                <div
                  key={index}
                  className="h-16 animate-pulse rounded-lg border border-zinc-800 bg-zinc-900"
                />
              ))}
            </div>
          ) : notes.length === 0 ? (
            <div className="rounded-lg border border-zinc-800 bg-[#091328] p-4 text-sm text-zinc-400">
              No notes found for the current filter.
            </div>
          ) : (
            <div
              className={
                filters.viewMode === "grid"
                  ? "grid grid-cols-1 gap-2"
                  : "space-y-2"
              }
            >
              {notes.map((note) => {
                const isActive = selectedNote?.id === note.id;
                const preview = stripHtmlTags(note.content).slice(0, 140);

                return (
                  <button
                    key={note.id}
                    type="button"
                    onClick={() => setSelectedNote(note)}
                    className={`w-full rounded-lg border p-3 text-left transition ${
                      isActive
                        ? "border-[#94aaff]/45 bg-[#141f38]"
                        : "border-zinc-800 bg-[#091328] hover:border-zinc-600"
                    }`}
                  >
                    <p className="line-clamp-1 text-sm font-semibold text-zinc-100">{note.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-zinc-400">{preview || "No content"}</p>
                    <div className="mt-2 flex items-center justify-between text-[10px] uppercase tracking-wider text-zinc-500">
                      <span>V{note.version}</span>
                      <span>{new Date(note.updated_at).toLocaleDateString()}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <NoteEditor
          note={selectedNote}
          title={draft.title}
          content={draft.content}
          selectedTagIds={draft.tagIds}
          tags={tags}
          isSaving={isSavingState}
          lastSavedAt={lastSavedAt}
          autoSaveError={autoSaveError}
          onTitleChange={(title) => setDraft((prev) => ({ ...prev, title }))}
          onContentChange={(content) => setDraft((prev) => ({ ...prev, content }))}
          onToggleTag={(tagId) => {
            setDraft((prev) => {
              const exists = prev.tagIds.includes(tagId);
              return {
                ...prev,
                tagIds: exists
                  ? prev.tagIds.filter((id) => id !== tagId)
                  : [...prev.tagIds, tagId],
              };
            });
          }}
          onDelete={handleDeleteSelected}
          isDeleting={isDeleting}
        />
      </div>
    </div>
  );
}