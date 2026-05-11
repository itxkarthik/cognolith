"use client";

import { FilePlus2, LayoutTemplate } from "lucide-react";

import type { NoteTemplateData } from "@/types";

const DEFAULT_NOTE_TEMPLATES: NoteTemplateData[] = [
	{
		id: "meeting",
		name: "Meeting Intel",
		description: "Structured capture for decisions, blockers, and follow-ups.",
		tags: ["meeting", "tasks"],
		content: `<h2>Meeting Context</h2><p>Purpose:</p><p>Participants:</p><p>Date:</p><h3>Key Decisions</h3><ul><li></li></ul><h3>Action Items</h3><ul><li><strong>Owner:</strong>  <strong>Due:</strong> </li></ul><h3>Risks / Blockers</h3><ul><li></li></ul>`,
	},
	{
		id: "research",
		name: "Research Lab",
		description: "Hypothesis-driven template for experiments and findings.",
		tags: ["research", "analysis"],
		content: `<h2>Research Question</h2><p></p><h3>Hypothesis</h3><p></p><h3>Findings</h3><ul><li></li></ul><h3>Evidence Links</h3><ul><li></li></ul><h3>Next Iteration</h3><p></p>`,
	},
	{
		id: "study",
		name: "Study Sprint",
		description: "Learning notes with concepts, examples, and memory hooks.",
		tags: ["study", "learning"],
		content: `<h2>Topic</h2><p></p><h3>Core Concepts</h3><ul><li></li></ul><h3>Examples</h3><ul><li></li></ul><h3>Flash Recall</h3><p>What should I remember tomorrow?</p>`,
	},
];

interface NoteTemplatesProps {
	onUseTemplate: (template: NoteTemplateData) => void;
	templates?: NoteTemplateData[];
}

export function NoteTemplates({ onUseTemplate, templates = DEFAULT_NOTE_TEMPLATES }: NoteTemplatesProps) {
	return (
		<section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6 backdrop-blur">
			<div className="mb-3 flex items-center gap-2">
				<LayoutTemplate className="h-4 w-4 text-cyan-200/80" />
				<p className="text-xs uppercase tracking-[0.2em] text-cyan-300/60">Templates</p>
			</div>
			<div className="grid gap-3 md:grid-cols-3">
				{templates.map((template) => (
					<button
						key={template.id}
						type="button"
						onClick={() => onUseTemplate(template)}
						className="group rounded-lg border border-cyan-500/20 bg-[#01040f] p-3 text-left transition hover:border-cyan-400/45 hover:bg-cyan-500/8"
					>
						<div className="flex items-center justify-between">
							<p className="text-sm font-semibold text-cyan-50">{template.name}</p>
							<FilePlus2 className="h-4 w-4 text-cyan-300/50 transition group-hover:text-cyan-200" />
						</div>
						<p className="mt-1 text-xs text-cyan-100/60">{template.description}</p>
						<div className="mt-2 flex flex-wrap gap-1">
							{template.tags.map((tag) => (
								<span
									key={`${template.id}-${tag}`}
									className="rounded-full border border-cyan-500/25 bg-cyan-500/8 px-2 py-0.5 text-[10px] uppercase tracking-wider text-cyan-100/70"
								>
									{tag}
								</span>
							))}
						</div>
					</button>
				))}
			</div>
		</section>
	);
}

export function getDefaultNoteTemplates(): NoteTemplateData[] {
	return DEFAULT_NOTE_TEMPLATES;
}
