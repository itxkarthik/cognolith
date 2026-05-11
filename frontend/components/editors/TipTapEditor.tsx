"use client";

import { useEffect } from "react";
import {
	Bold,
	Code2,
	Heading2,
	Italic,
	List,
	ListOrdered,
	Redo2,
	Undo2,
} from "lucide-react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

import { cn } from "@/lib/utils/cn";

interface TipTapEditorProps {
	value: string;
	onChange: (value: string) => void;
	editable?: boolean;
	className?: string;
}

interface ToolbarButtonProps {
	onClick: () => void;
	active?: boolean;
	disabled?: boolean;
	ariaLabel: string;
	children: React.ReactNode;
}

function ToolbarButton({
	onClick,
	active = false,
	disabled = false,
	ariaLabel,
	children,
}: ToolbarButtonProps) {
	return (
		<button
			type="button"
			onClick={onClick}
			disabled={disabled}
			aria-label={ariaLabel}
			className={cn(
				"inline-flex h-8 w-8 items-center justify-center rounded-md border text-cyan-100/75 transition",
				active
					? "border-cyan-400/60 bg-cyan-500/18 text-cyan-100"
					: "border-cyan-500/28 bg-[#020611] hover:border-cyan-400/50 hover:bg-cyan-500/10",
				disabled && "cursor-not-allowed opacity-50"
			)}
		>
			{children}
		</button>
	);
}

export function TipTapEditor({
	value,
	onChange,
	editable = true,
	className,
}: TipTapEditorProps) {
	const editor = useEditor({
		extensions: [
			StarterKit.configure({
				heading: {
					levels: [1, 2, 3],
				},
			}),
		],
		content: value || "<p></p>",
		editable,
		editorProps: {
			attributes: {
				class:
					"min-h-[260px] max-h-[55vh] overflow-y-auto rounded-b-xl bg-[#020611] px-4 py-4 text-sm leading-7 text-cyan-50 focus:outline-none",
			},
		},
		onUpdate: ({ editor: currentEditor }) => {
			onChange(currentEditor.getHTML());
		},
		immediatelyRender: false,
	});

	useEffect(() => {
		if (!editor) {
			return;
		}

		const current = editor.getHTML();
		if (value !== current) {
			editor.commands.setContent(value || "<p></p>", { emitUpdate: false });
		}
	}, [editor, value]);

	if (!editor) {
		return (
			<div className="rounded-xl border border-cyan-500/20 bg-[#020611]/90 p-4 text-sm text-cyan-100/60">
				Loading editor...
			</div>
		);
	}

	return (
		<div className={cn("overflow-hidden rounded-xl border border-cyan-500/20", className)}>
			<div className="flex flex-wrap items-center gap-2 border-b border-cyan-500/20 bg-[#041022] px-3 py-2">
				<ToolbarButton
					ariaLabel="Undo"
					onClick={() => editor.chain().focus().undo().run()}
					disabled={!editor.can().undo()}
				>
					<Undo2 className="h-4 w-4" />
				</ToolbarButton>
				<ToolbarButton
					ariaLabel="Redo"
					onClick={() => editor.chain().focus().redo().run()}
					disabled={!editor.can().redo()}
				>
					<Redo2 className="h-4 w-4" />
				</ToolbarButton>
				<div className="mx-1 h-6 w-px bg-cyan-500/25" />
				<ToolbarButton
					ariaLabel="Bold"
					onClick={() => editor.chain().focus().toggleBold().run()}
					active={editor.isActive("bold")}
				>
					<Bold className="h-4 w-4" />
				</ToolbarButton>
				<ToolbarButton
					ariaLabel="Italic"
					onClick={() => editor.chain().focus().toggleItalic().run()}
					active={editor.isActive("italic")}
				>
					<Italic className="h-4 w-4" />
				</ToolbarButton>
				<ToolbarButton
					ariaLabel="Heading"
					onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
					active={editor.isActive("heading", { level: 2 })}
				>
					<Heading2 className="h-4 w-4" />
				</ToolbarButton>
				<ToolbarButton
					ariaLabel="Bullet list"
					onClick={() => editor.chain().focus().toggleBulletList().run()}
					active={editor.isActive("bulletList")}
				>
					<List className="h-4 w-4" />
				</ToolbarButton>
				<ToolbarButton
					ariaLabel="Ordered list"
					onClick={() => editor.chain().focus().toggleOrderedList().run()}
					active={editor.isActive("orderedList")}
				>
					<ListOrdered className="h-4 w-4" />
				</ToolbarButton>
				<ToolbarButton
					ariaLabel="Code block"
					onClick={() => editor.chain().focus().toggleCodeBlock().run()}
					active={editor.isActive("codeBlock")}
				>
					<Code2 className="h-4 w-4" />
				</ToolbarButton>
			</div>
			<EditorContent editor={editor} />
		</div>
	);
}
