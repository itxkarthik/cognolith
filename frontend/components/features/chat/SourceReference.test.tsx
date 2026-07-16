import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ChatSources } from "@/types";

import { SourceReference } from "./SourceReference";


describe("SourceReference", () => {
	it("renders citation numbers and does not fabricate an inventory score", () => {
		const sources = {
			documents: [],
			chunks: [],
			notes: [
				{
					note_id: 7,
					title: "Beacon",
					score: null,
					hybrid_score: null,
					preview: "A reporting project.",
					citation_id: 2,
					origin: "inventory",
				},
			],
		} as unknown as ChatSources;

		const markup = renderToStaticMarkup(<SourceReference sources={sources} />);

		expect(markup).toContain("[2]");
		expect(markup).toContain("Beacon");
		expect(markup).not.toContain("workspace overview");
		expect(markup).not.toContain("score 0.00");
	});

	it("renders grouped document citation numbers and only cited chunks", () => {
		const sources = {
			documents: [
				{
					document_id: 4,
					title: "Atlas brief",
					chunk_count: 1,
					max_score: 0.84,
					citation_ids: [1],
					origin: "vector",
				},
			],
			chunks: [
				{
					chunk_id: 8,
					document_id: 4,
					document_title: "Atlas brief",
					chunk_index: 2,
					score: 0.84,
					hybrid_score: 0.79,
					preview: "The release window is Friday.",
					citation_id: 1,
					origin: "vector",
				},
			],
			notes: [],
		} as unknown as ChatSources;

		const markup = renderToStaticMarkup(<SourceReference sources={sources} />);

		expect(markup).toContain("[1]");
		expect(markup).toContain("Atlas brief");
		expect(markup).toContain("score 0.84");
		expect(markup).toContain("The release window is Friday.");
	});

	it("labels exact hybrid matches and merged chunk ranges without a low score", () => {
		const sources = {
			documents: [
				{
					document_id: 22,
					title: "Karthik Das P CV",
					chunk_count: 3,
					max_score: null,
					citation_ids: [1],
					origin: "hybrid",
				},
			],
			chunks: [
				{
					chunk_id: 46,
					document_id: 22,
					document_title: "Karthik Das P CV",
					chunk_index: 3,
					chunk_end_index: 5,
					score: null,
					hybrid_score: 0.82,
					preview: "GoTorrent project details.",
					citation_id: 1,
					origin: "hybrid",
				},
			],
			notes: [],
		} satisfies ChatSources;

		const markup = renderToStaticMarkup(<SourceReference sources={sources} />);

		expect(markup).toContain("Exact match");
		expect(markup).toContain("chunks 3-5");
		expect(markup).not.toContain("score 0.65");
	});
});
