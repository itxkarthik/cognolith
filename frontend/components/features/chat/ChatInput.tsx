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
		<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-3 backdrop-blur">
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
					className="w-full resize-none rounded-lg border border-cyan-500/30 bg-cyan-500/5 px-3 py-2 text-sm text-cyan-50 placeholder:text-cyan-300/45 focus:border-cyan-400/60 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
				/>

				<button
					type="button"
					onClick={() => {
						void handleSubmit();
					}}
					disabled={disabled || !content.trim()}
					className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-cyan-400/40 bg-cyan-300 text-slate-900 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
					aria-label="Send message"
				>
					{disabled ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
				</button>
			</div>
		</section>
	);
}
