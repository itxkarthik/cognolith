"use client";

import { useNoteStore } from "@/store/noteStore";

export function useNoteFolders() {
	const folders = useNoteStore((state) => state.folders);
	const selectedFolderId = useNoteStore((state) => state.filters.folderId);
	const setFolderFilter = useNoteStore((state) => state.setFolderFilter);
	const createFolder = useNoteStore((state) => state.createFolder);
	const fetchFolders = useNoteStore((state) => state.fetchFolders);

	return {
		folders,
		selectedFolderId,
		setFolderFilter,
		createFolder,
		fetchFolders,
	};
}
