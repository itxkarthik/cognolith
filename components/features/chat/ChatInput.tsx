"use client";

import { ArrowUp, Loader2 } from "lucide-react";
import { useState } from "react";

interface ChatInputProps {
	onSend: (content: string) => Promise<void>;
	disabled?: boolean;
}

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
	const [content, setContent] = useState("");

	const handleSubmit = async () => {
		const trimmed = content.trim();
		if (!trimmed || disabled) {
			return;
		}

		await onSend(trimmed);
		setContent("");
	};

	return (
		<section className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-3">
			<div className="flex items-end gap-2">
				<textarea
					value={content}
					onChange={(event) => setContent(event.target.value)}
					onKeyDown={(event) => {
						if (event.key === "Enter" && !event.shiftKey) {
							event.preventDefault();
							void handleSubmit();
						}
					}}
					rows={3}
					disabled={disabled}
					placeholder="Ask about your documents, notes, or chat history..."
					className="w-full resize-none rounded-lg border border-zinc-700 bg-[#091328] px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-[#94aaff]/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
				/>

				<button
					type="button"
					onClick={() => {
						void handleSubmit();
					}}
					disabled={disabled || !content.trim()}
					className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-[#4f5a8f] bg-[#18233f] text-[#dbe3ff] transition hover:border-[#94aaff]/45 disabled:cursor-not-allowed disabled:opacity-50"
					aria-label="Send message"
				>
					{disabled ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
				</button>
			</div>
		</section>
	);
}
