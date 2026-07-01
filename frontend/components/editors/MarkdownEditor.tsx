"use client";

import { useEffect, useRef } from "react";
import { Bold, Code2, Heading2, Italic, Link2, List, ListOrdered, Quote } from "lucide-react";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { EditorSelection, EditorState } from "@codemirror/state";
import {
  drawSelection,
  EditorView,
  keymap,
  placeholder,
} from "@codemirror/view";

import { cn } from "@/lib/utils/cn";
import { markdownLivePreview } from "@/components/editors/markdownLivePreview";

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  editable?: boolean;
  className?: string;
}

interface ToolbarButtonProps {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}

function ToolbarButton({ label, onClick, children }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-border bg-background text-muted-foreground transition hover:bg-accent hover:text-foreground active:translate-y-px focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      {children}
    </button>
  );
}

export function MarkdownEditor({ value, onChange, editable = true, className }: MarkdownEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const initialValueRef = useRef(value);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!hostRef.current) return;

    const view = new EditorView({
      parent: hostRef.current,
      state: EditorState.create({
        doc: initialValueRef.current,
        extensions: [
          markdown(),
          history(),
          drawSelection(),
          markdownLivePreview,
          keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap]),
          placeholder("Start writing in Markdown..."),
          EditorView.editable.of(editable),
          EditorView.contentAttributes.of({ "aria-label": "Markdown note editor" }),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) onChangeRef.current(update.state.doc.toString());
          }),
        ],
      }),
    });
    viewRef.current = view;

    const navigate = (event: Event) => {
      const offset = Math.min(
        Math.max(0, (event as CustomEvent<number>).detail),
        view.state.doc.length
      );
      view.dispatch({
        selection: EditorSelection.cursor(offset),
        effects: EditorView.scrollIntoView(offset, { y: "center" }),
      });
      view.focus();
    };
    window.addEventListener("note-editor:navigate", navigate);

    return () => {
      window.removeEventListener("note-editor:navigate", navigate);
      view.destroy();
      viewRef.current = null;
    };
  }, [editable]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
  }, [value]);

  const replaceSelection = (prefix: string, suffix = "", placeholderText = "text") => {
    const view = viewRef.current;
    if (!view) return;
    const range = view.state.selection.main;
    const selected = view.state.sliceDoc(range.from, range.to) || placeholderText;
    view.dispatch({
      changes: { from: range.from, to: range.to, insert: `${prefix}${selected}${suffix}` },
      selection: EditorSelection.range(range.from + prefix.length, range.from + prefix.length + selected.length),
    });
    view.focus();
  };

  const prefixLines = (prefix: string) => {
    const view = viewRef.current;
    if (!view) return;
    const range = view.state.selection.main;
    const start = view.state.doc.lineAt(range.from).from;
    const end = range.empty ? view.state.doc.lineAt(range.to).to : range.to;
    const selected = view.state.sliceDoc(start, end) || "List item";
    const replacement = selected
      .split("\n")
      .map((line, index) => `${prefix === "1. " ? `${index + 1}. ` : prefix}${line}`)
      .join("\n");
    view.dispatch({
      changes: { from: start, to: end, insert: replacement },
      selection: EditorSelection.range(start, start + replacement.length),
    });
    view.focus();
  };

  return (
    <div className={cn("overflow-hidden border border-border bg-background", className)}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted px-3 py-2">
        <ToolbarButton label="Heading" onClick={() => prefixLines("## ")}>
          <Heading2 className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Bold" onClick={() => replaceSelection("**", "**")}>
          <Bold className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Italic" onClick={() => replaceSelection("*", "*")}>
          <Italic className="h-4 w-4" />
        </ToolbarButton>
        <div className="mx-1 h-6 w-px bg-border" />
        <ToolbarButton label="Bullet list" onClick={() => prefixLines("- ")}>
          <List className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Numbered list" onClick={() => prefixLines("1. ")}>
          <ListOrdered className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Quote" onClick={() => prefixLines("> ")}>
          <Quote className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Code" onClick={() => replaceSelection("`", "`", "code")}>
          <Code2 className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton label="Link note" onClick={() => replaceSelection("[[", "]]", "Note title")}>
          <Link2 className="h-4 w-4" />
        </ToolbarButton>
        <span className="ml-auto hidden text-[10px] text-muted-foreground sm:inline">LIVE PREVIEW</span>
      </div>
      <div ref={hostRef} id="note-markdown-editor" />
    </div>
  );
}
