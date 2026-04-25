"use client";

import { useEffect } from "react";

import { useNoteStore } from "@/store/noteStore";

export function useNotes() {
	const notes = useNoteStore((state) => state.notes);
	const total = useNoteStore((state) => state.total);
	const selectedNote = useNoteStore((state) => state.selectedNote);
	const folders = useNoteStore((state) => state.folders);
	const tags = useNoteStore((state) => state.tags);
	const filters = useNoteStore((state) => state.filters);
	const isLoading = useNoteStore((state) => state.isLoading);
	const isSaving = useNoteStore((state) => state.isSaving);
	const isDeleting = useNoteStore((state) => state.isDeleting);
	const error = useNoteStore((state) => state.error);

	const fetchNotes = useNoteStore((state) => state.fetchNotes);
	const fetchNoteById = useNoteStore((state) => state.fetchNoteById);
	const createNote = useNoteStore((state) => state.createNote);
	const updateNoteById = useNoteStore((state) => state.updateNoteById);
	const deleteNoteById = useNoteStore((state) => state.deleteNoteById);
	const fetchFolders = useNoteStore((state) => state.fetchFolders);
	const fetchTags = useNoteStore((state) => state.fetchTags);
	const createFolder = useNoteStore((state) => state.createFolder);
	const createTag = useNoteStore((state) => state.createTag);
	const setSelectedNote = useNoteStore((state) => state.setSelectedNote);
	const setSearch = useNoteStore((state) => state.setSearch);
	const setFolderFilter = useNoteStore((state) => state.setFolderFilter);
	const setTagFilter = useNoteStore((state) => state.setTagFilter);
	const setViewMode = useNoteStore((state) => state.setViewMode);
	const clearError = useNoteStore((state) => state.clearError);

	useEffect(() => {
		void fetchFolders();
		void fetchTags();
	}, [fetchFolders, fetchTags]);

	useEffect(() => {
		void fetchNotes({
			search: filters.search || undefined,
			folder_id: filters.folderId ?? undefined,
			tag_id: filters.tagId ?? undefined,
			skip: 0,
			limit: filters.limit,
		});
	}, [fetchNotes, filters.folderId, filters.limit, filters.search, filters.tagId]);

	return {
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
		fetchNotes,
		fetchNoteById,
		createNote,
		updateNoteById,
		deleteNoteById,
		fetchFolders,
		fetchTags,
		createFolder,
		createTag,
		setSelectedNote,
		setSearch,
		setFolderFilter,
		setTagFilter,
		setViewMode,
		clearError,
	};
}
