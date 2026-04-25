"use client";

import { useEffect, useRef } from "react";

import type { ChatMessageResponse } from "@/types";

import { ChatMessage } from "./ChatMessage";

interface ChatHistoryProps {
	messages: ChatMessageResponse[];
	isLoading?: boolean;
	streamingMessageId?: number | null;
}

export function ChatHistory({
	messages,
	isLoading = false,
	streamingMessageId = null,
}: ChatHistoryProps) {
	const bottomAnchorRef = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		bottomAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
	}, [messages, streamingMessageId]);

	if (isLoading && messages.length === 0) {
		return (
			<section className="h-[56vh] space-y-2 overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3 backdrop-blur">
				{Array.from({ length: 6 }).map((_, index) => (
					<div
						key={index}
						className="h-16 animate-pulse rounded-lg border border-zinc-800 bg-zinc-950"
					/>
				))}
			</section>
		);
	}

	return (
		<section className="h-[56vh] overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3 backdrop-blur">
			{messages.length === 0 ? (
				<div className="flex h-full items-center justify-center rounded-lg border border-dashed border-zinc-700 bg-zinc-950 p-5 text-sm text-zinc-400">
					Start with a question. Answers will include source references from your library.
				</div>
			) : (
				<div className="space-y-3">
					{messages.map((message) => (
						<ChatMessage
							key={message.id}
							message={message}
							isStreaming={streamingMessageId === message.id}
						/>
					))}
					<div ref={bottomAnchorRef} />
				</div>
			)}
		</section>
	);
}
