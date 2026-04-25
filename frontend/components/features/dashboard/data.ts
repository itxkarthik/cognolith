import {
	Brain,
	FileText,
	FolderKanban,
	MessageSquare,
	NotebookPen,
	Search,
	Upload,
} from "lucide-react";

import type { DashboardLinkItem } from "@/components/features/dashboard/types";

export const dashboardCards: DashboardLinkItem[] = [
	{
		title: "Notes",
		description: "Capture ideas, summaries, and linked insights.",
		href: "/dashboard/notes",
		icon: FileText,
	},
	{
		title: "Documents",
		description: "Ingest PDFs and text sources for retrieval.",
		href: "/dashboard/documents",
		icon: FolderKanban,
	},
	{
		title: "Chat",
		description: "Ask questions and convert insights into notes.",
		href: "/dashboard/chat",
		icon: MessageSquare,
	},
	{
		title: "Knowledge Graph",
		description: "Visualize relationships across your knowledge base.",
		href: "/dashboard/knowledge-graph",
		icon: Brain,
	},
];

export const dashboardQuickActions: DashboardLinkItem[] = [
	{
		title: "Create Note",
		description: "Capture a new idea before it gets lost.",
		href: "/dashboard/notes/new",
		icon: NotebookPen,
	},
	{
		title: "Upload Document",
		description: "Add a file for extraction and retrieval.",
		href: "/dashboard/documents/upload",
		icon: Upload,
	},
	{
		title: "Start Chat",
		description: "Ask your assistant about your knowledge base.",
		href: "/dashboard/chat",
		icon: MessageSquare,
	},
	{
		title: "Global Search",
		description: "Find notes, docs, and chats in one place.",
		href: "/dashboard/search",
		icon: Search,
	},
];
