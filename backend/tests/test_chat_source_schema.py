from app.schemas.chat import ChatSources


def test_new_citation_metadata_survives_source_validation() -> None:
    sources = ChatSources.model_validate(
        {
            "documents": [],
            "chunks": [],
            "notes": [
                {
                    "note_id": 7,
                    "title": "Atlas",
                    "score": None,
                    "hybrid_score": None,
                    "preview": "A project overview.",
                    "citation_id": 2,
                    "origin": "inventory",
                }
            ],
        }
    )

    note = sources.notes[0]
    assert note.citation_id == 2
    assert note.origin == "inventory"
    assert note.score is None


def test_legacy_source_payload_remains_valid() -> None:
    sources = ChatSources.model_validate(
        {
            "documents": [
                {
                    "document_id": 4,
                    "title": "Legacy document",
                    "chunk_count": 1,
                    "max_score": 0.78,
                }
            ],
            "chunks": [
                {
                    "chunk_id": 8,
                    "document_id": 4,
                    "document_title": "Legacy document",
                    "chunk_index": 0,
                    "score": 0.78,
                    "preview": "Legacy preview",
                }
            ],
            "notes": [],
        }
    )

    assert sources.documents[0].citation_ids == []
    assert sources.documents[0].origin == "vector"
    assert sources.chunks[0].citation_id is None


def test_hybrid_source_preserves_merged_chunk_range() -> None:
    sources = ChatSources.model_validate(
        {
            "documents": [
                {
                    "document_id": 22,
                    "title": "Karthik Das P CV",
                    "chunk_count": 3,
                    "max_score": None,
                    "citation_ids": [1],
                    "origin": "hybrid",
                }
            ],
            "chunks": [
                {
                    "chunk_id": 46,
                    "document_id": 22,
                    "document_title": "Karthik Das P CV",
                    "chunk_index": 3,
                    "chunk_end_index": 5,
                    "score": None,
                    "hybrid_score": 0.82,
                    "preview": "GoTorrent project details",
                    "citation_id": 1,
                    "origin": "hybrid",
                }
            ],
            "notes": [],
        }
    )

    assert sources.documents[0].origin == "hybrid"
    assert sources.chunks[0].chunk_end_index == 5
