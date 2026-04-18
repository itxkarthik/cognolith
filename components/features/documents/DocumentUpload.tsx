"use client";

import { FileUp, UploadCloud } from "lucide-react";
import { useState } from "react";

import { useDocumentStore } from "@/store/documentStore";
import type { DocumentResponse } from "@/types";

interface DocumentUploadProps {
	onSuccess?: (document: DocumentResponse) => void;
}

export function DocumentUpload({ onSuccess }: DocumentUploadProps) {
	const uploadDocumentFile = useDocumentStore((state) => state.uploadDocumentFile);
	const isUploading = useDocumentStore((state) => state.isUploading);
	const storeError = useDocumentStore((state) => state.error);

	const [file, setFile] = useState<File | null>(null);
	const [title, setTitle] = useState("");
	const [tags, setTags] = useState("");
	const [language, setLanguage] = useState("en");
	const [localError, setLocalError] = useState<string | null>(null);

	const errorMessage = localError ?? storeError;

	const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setLocalError(null);

		if (!file) {
			setLocalError("Please choose a document file to upload.");
			return;
		}

		const parsedTags = tags
			.split(",")
			.map((tag) => tag.trim())
			.filter(Boolean);

		try {
			const uploadedDocument = await uploadDocumentFile({
				file,
				title: title.trim() || undefined,
				tags: parsedTags,
				language: language.trim() || "en",
			});

			setFile(null);
			setTitle("");
			setTags("");
			onSuccess?.(uploadedDocument);
		} catch {
			// Errors are handled by store and local UI messaging.
		}
	};

	return (
		<form
			onSubmit={handleSubmit}
			className="space-y-5 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-6"
		>
			<div>
				<p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Upload</p>
				<h2 className="mt-2 text-xl font-semibold text-zinc-100">Add a new document</h2>
				<p className="mt-1 text-sm text-zinc-300">
					Supported formats: PDF, DOCX, Markdown, and TXT.
				</p>
			</div>

			<div className="space-y-2">
				<label htmlFor="document-file" className="text-sm font-medium text-zinc-200">
					Document file
				</label>
				<div className="rounded-xl border border-dashed border-zinc-700 bg-zinc-950/60 p-4">
					<input
						id="document-file"
						type="file"
						accept=".pdf,.docx,.md,.txt,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
						onChange={(event) => {
							setFile(event.target.files?.[0] ?? null);
						}}
						className="block w-full text-sm text-zinc-300 file:mr-4 file:rounded-lg file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-sm file:font-medium file:text-zinc-100 hover:file:bg-zinc-700"
					/>
					{file ? (
						<p className="mt-2 inline-flex items-center gap-2 text-xs text-zinc-400">
							<FileUp className="h-3.5 w-3.5" />
							{file.name}
						</p>
					) : null}
				</div>
			</div>

			<div className="grid gap-4 md:grid-cols-2">
				<div className="space-y-2">
					<label htmlFor="document-title" className="text-sm font-medium text-zinc-200">
						Title (optional)
					</label>
					<input
						id="document-title"
						type="text"
						value={title}
						onChange={(event) => setTitle(event.target.value)}
						placeholder="Leave blank to use filename"
						className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-500 focus:outline-none"
					/>
				</div>

				<div className="space-y-2">
					<label htmlFor="document-language" className="text-sm font-medium text-zinc-200">
						Language
					</label>
					<input
						id="document-language"
						type="text"
						value={language}
						onChange={(event) => setLanguage(event.target.value)}
						placeholder="en"
						className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-500 focus:outline-none"
					/>
				</div>
			</div>

			<div className="space-y-2">
				<label htmlFor="document-tags" className="text-sm font-medium text-zinc-200">
					Tags (comma separated)
				</label>
				<input
					id="document-tags"
					type="text"
					value={tags}
					onChange={(event) => setTags(event.target.value)}
					placeholder="research, planning, handbook"
					className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-500 focus:outline-none"
				/>
			</div>

			{errorMessage ? (
				<p className="rounded-lg border border-rose-800/60 bg-rose-950/30 px-3 py-2 text-sm text-rose-200">
					{errorMessage}
				</p>
			) : null}

			<button
				type="submit"
				disabled={isUploading}
				className="inline-flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-60"
			>
				<UploadCloud className="h-4 w-4" />
				{isUploading ? "Uploading..." : "Upload document"}
			</button>
		</form>
	);
}
