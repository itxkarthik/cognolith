from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import ColumnElement, func, update
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, or_, select

from app.models.document import Document
from app.models.note import NoteFolders, NoteLinks, NoteLinkType, Notes, NoteTagRelations, NoteTags
from app.models.user import User
from app.schemas.note import FolderCreate, FolderUpdate, NoteCreate, NoteUpdate, TagCreate
from app.utils.sanitization import strip_all_html
from app.utils.search import contains_ignoring_case
from app.utils.text_processing import (
    create_content_preview,
    extract_wiki_link_titles,
    markdown_to_plain_text,
    normalize_markdown,
)

# Autosave fires after every typing pause; one snapshot per window keeps history
# useful without a row per keystroke burst.
NOTE_VERSION_INTERVAL = timedelta(minutes=10)
NOTE_VERSION_RETENTION = 50
_VERSIONED_FIELDS = {"title", "content"}


def create_note(*, session: Session, current_user: User, payload: NoteCreate) -> Notes:
    user_id = _require_persisted_id(current_user.id, "User")
    _validate_folder_access(session=session, user_id=user_id, folder_id=payload.folder_id)
    _validate_document_access(
        session=session, user_id=user_id, document_id=payload.linked_document_id
    )

    clean_content = (
        payload.content if payload.content_type == "html" else normalize_markdown(payload.content)
    )
    preview_source = (
        strip_all_html(clean_content)
        if payload.content_type == "html"
        else markdown_to_plain_text(clean_content)
    )
    note = Notes(
        user_id=user_id,
        folder_id=payload.folder_id,
        title=payload.title,
        content=clean_content,
        content_type=payload.content_type,
        content_preview=create_content_preview(preview_source, max_length=200),
        keywords=payload.keywords,
        is_favorite=payload.is_favorite,
        is_pinned=payload.is_pinned,
        linked_document_id=payload.linked_document_id,
        linked_chat_session_id=payload.linked_chat_session_id,
        word_count=len(preview_source.split()),
        char_count=len(preview_source),
        read_time_minutes=(max(1, len(preview_source.split()) // 200) if preview_source else 1),
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    note_id = _require_persisted_id(note.id, "Note")

    if payload.tag_ids:
        assign_tags_to_note(
            session=session,
            current_user=current_user,
            note_id=note_id,
            tag_ids=payload.tag_ids,
        )

    if payload.linked_note_ids:
        link_notes(
            session=session,
            current_user=current_user,
            source_note_id=note_id,
            target_note_ids=payload.linked_note_ids,
        )

    sync_wiki_links(
        session=session,
        current_user=current_user,
        source_note_id=note_id,
        content=clean_content,
    )

    return get_note_by_id(session=session, current_user=current_user, note_id=note_id)


def list_notes(
    *,
    session: Session,
    current_user: User,
    folder_id: int | None = None,
    tag_id: int | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Notes], int]:
    """
    List notes with efficient database queries.

    Performance improvements:
    - Uses joinedload to eagerly fetch tags (prevents N+1 queries)
    - Uses SQL COUNT(*) for efficient counting (not fetching all rows)
    - Applies LIMIT/OFFSET at database level for pagination
    """
    # Build base statement with filters
    base_where = [Notes.user_id == current_user.id, col(Notes.is_deleted).is_not(True)]

    if folder_id is not None:
        base_where.append(Notes.folder_id == folder_id)

    if tag_id is not None:
        tagged_note_ids = select(NoteTagRelations.note_id).where(NoteTagRelations.tag_id == tag_id)
        base_where.append(col(Notes.id).in_(tagged_note_ids))

    if search:
        base_where.append(
            or_(
                contains_ignoring_case(Notes.title, search),
                contains_ignoring_case(Notes.content, search),
            )
        )

    # For counting: use SELECT COUNT(*) without joinedload
    count_statement = select(func.count()).select_from(Notes).where(*base_where)
    total_count = session.exec(count_statement).one() or 0

    # For fetching data: include eager loading and pagination
    statement = select(Notes).where(*base_where)
    statement = statement.options(joinedload(Notes.tags))  # pyright: ignore[reportArgumentType]
    statement = statement.order_by(col(Notes.updated_at).desc())
    statement = statement.limit(limit).offset(skip)

    notes = session.exec(statement).unique().all()

    return list(notes), total_count


def list_folders(*, session: Session, current_user: User) -> list[NoteFolders]:
    statement = (
        select(NoteFolders)
        .where(
            NoteFolders.user_id == current_user.id,
            col(NoteFolders.is_deleted).is_not(True),
        )
        .order_by(col(NoteFolders.sort_order).asc(), col(NoteFolders.name).asc())
    )
    return list(session.exec(statement).all())


def list_tags(*, session: Session, current_user: User) -> list[NoteTags]:
    statement = (
        select(NoteTags)
        .where(NoteTags.user_id == current_user.id)
        .order_by(col(NoteTags.name).asc())
    )
    return list(session.exec(statement).all())


def get_note_by_id(*, session: Session, current_user: User, note_id: int) -> Notes:
    note = (
        session.exec(
            select(Notes)
            .where(
                Notes.id == note_id,
                Notes.user_id == current_user.id,
                col(Notes.is_deleted).is_not(True),
            )
            .options(joinedload(Notes.tags))  # pyright: ignore[reportArgumentType]
        )
        .unique()
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def update_note(
    *, session: Session, current_user: User, note_id: int, payload: NoteUpdate
) -> Notes:
    user_id = _require_persisted_id(current_user.id, "User")
    note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return note

    _validate_folder_access(
        session=session, user_id=user_id, folder_id=update_data.get("folder_id")
    )
    _validate_document_access(
        session=session,
        user_id=user_id,
        document_id=update_data.get("linked_document_id"),
    )

    if _should_snapshot(session=session, note=note, update_data=update_data):
        snapshot = _create_version_snapshot(session=session, note=note)
        note.previous_version_id = snapshot.id
        note.version = (note.version or 1) + 1

    for field_name, value in update_data.items():
        if field_name in {"tag_ids", "linked_note_ids"}:
            continue
        if field_name == "content" and value is not None:
            resolved_content_type = update_data.get("content_type", note.content_type)
            cleaned = value if resolved_content_type == "html" else normalize_markdown(value)
            preview_source = (
                strip_all_html(cleaned)
                if resolved_content_type == "html"
                else markdown_to_plain_text(cleaned)
            )
            note.content = cleaned
            note.content_preview = create_content_preview(preview_source, max_length=200)
            note.word_count = len(preview_source.split())
            note.char_count = len(preview_source)
            note.read_time_minutes = (
                max(1, len(preview_source.split()) // 200) if preview_source else 1
            )
            continue
        setattr(note, field_name, value)

    note.last_edited_at = datetime.now(UTC)

    # Snapshot, pruning and update commit together, so a failed update leaves no orphan
    session.add(note)
    _prune_version_history(session=session, note=note)
    session.commit()
    session.refresh(note)
    persisted_note_id = _require_persisted_id(note.id, "Note")

    if payload.tag_ids is not None:
        assign_tags_to_note(
            session=session,
            current_user=current_user,
            note_id=persisted_note_id,
            tag_ids=payload.tag_ids,
        )

    if payload.linked_note_ids is not None:
        sync_note_links(
            session=session,
            current_user=current_user,
            source_note_id=persisted_note_id,
            target_note_ids=payload.linked_note_ids,
        )

    if payload.content is not None:
        sync_wiki_links(
            session=session,
            current_user=current_user,
            source_note_id=persisted_note_id,
            content=note.content,
        )

    return get_note_by_id(session=session, current_user=current_user, note_id=persisted_note_id)


def soft_delete_note(*, session: Session, current_user: User, note_id: int) -> None:
    note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
    note.is_deleted = True
    note.is_archived = True
    session.add(note)
    session.commit()


def create_folder(*, session: Session, current_user: User, payload: FolderCreate) -> NoteFolders:
    user_id = _require_persisted_id(current_user.id, "User")
    _validate_folder_access(session=session, user_id=user_id, folder_id=payload.parent_folder_id)
    _ensure_folder_name_free(
        session=session, user_id=user_id, parent_id=payload.parent_folder_id, name=payload.name
    )
    folder = NoteFolders(
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        parent_folder_id=payload.parent_folder_id,
        color=payload.color,
        icon=payload.icon,
        emoji=payload.emoji,
    )
    session.add(folder)
    session.commit()
    session.refresh(folder)
    return folder


def update_folder(
    *, session: Session, current_user: User, folder_id: int, payload: FolderUpdate
) -> NoteFolders:
    user_id = _require_persisted_id(current_user.id, "User")
    folder = _get_folder(session=session, user_id=user_id, folder_id=folder_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise HTTPException(status_code=422, detail="Folder name cannot be empty")

    parent_id = changes.get("parent_folder_id", folder.parent_folder_id)
    if "parent_folder_id" in changes and parent_id is not None:
        _validate_folder_access(session=session, user_id=user_id, folder_id=parent_id)
        if parent_id in _folder_subtree_ids(session=session, user_id=user_id, root_id=folder_id):
            raise HTTPException(
                status_code=409, detail="A folder can't be moved into itself or its subfolders"
            )
    name = changes.get("name", folder.name)
    if name != folder.name or parent_id != folder.parent_folder_id:
        _ensure_folder_name_free(
            session=session, user_id=user_id, parent_id=parent_id, name=name, exclude_id=folder_id
        )

    for field, value in changes.items():
        setattr(folder, field, value)
    session.add(folder)
    session.commit()
    session.refresh(folder)
    return folder


def delete_folder(*, session: Session, current_user: User, folder_id: int) -> None:
    """
    Delete a folder and move its notes and subfolders up to its parent (the root for a
    top-level folder), in one transaction. Nothing inside is hidden or lost; a subfolder
    whose name is taken in the parent gets a numbered suffix.
    """
    user_id = _require_persisted_id(current_user.id, "User")
    folder = _get_folder(session=session, user_id=user_id, folder_id=folder_id)
    parent_id = folder.parent_folder_id

    session.exec(
        update(Notes)
        .where(col(Notes.user_id) == user_id, col(Notes.folder_id) == folder_id)
        .values(folder_id=parent_id)
    )
    children = session.exec(
        select(NoteFolders)
        .where(NoteFolders.user_id == user_id, NoteFolders.parent_folder_id == folder_id)
        .order_by(col(NoteFolders.name).asc(), col(NoteFolders.id).asc())
    ).all()
    taken = _folder_names(session=session, user_id=user_id, parent_id=parent_id)
    for child in children:
        child.name = _unique_folder_name(child.name, taken)
        taken.add(child.name)
        child.parent_folder_id = parent_id
        session.add(child)
    # Write the moves first: `subfolders` cascades delete-orphan, so the folder must
    # have no children left when it is deleted
    session.flush()
    session.expire(folder, ["subfolders", "notes"])
    # The emptied row is removed rather than flagged: a flagged row would still hold
    # its name in the unique (user, name, parent) constraint
    session.delete(folder)
    session.commit()


def _get_folder(*, session: Session, user_id: int, folder_id: int) -> NoteFolders:
    folder = session.exec(
        select(NoteFolders).where(
            NoteFolders.id == folder_id,
            NoteFolders.user_id == user_id,
            col(NoteFolders.is_deleted).is_not(True),
        )
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


def _in_folder_parent(parent_id: int | None) -> ColumnElement[bool]:
    column = col(NoteFolders.parent_folder_id)
    return column.is_(None) if parent_id is None else column == parent_id


def _folder_names(*, session: Session, user_id: int, parent_id: int | None) -> set[str]:
    # Soft-deleted rows count: the unique constraint covers them too
    return set(
        session.exec(
            select(NoteFolders.name).where(
                NoteFolders.user_id == user_id, _in_folder_parent(parent_id)
            )
        ).all()
    )


def _ensure_folder_name_free(
    *,
    session: Session,
    user_id: int,
    parent_id: int | None,
    name: str,
    exclude_id: int | None = None,
) -> None:
    statement = select(NoteFolders.id).where(
        NoteFolders.user_id == user_id, NoteFolders.name == name, _in_folder_parent(parent_id)
    )
    if exclude_id is not None:
        statement = statement.where(NoteFolders.id != exclude_id)
    if session.exec(statement).first() is not None:
        raise HTTPException(status_code=409, detail="A folder with this name already exists here")


def _unique_folder_name(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    suffix = 2
    while f"{name} ({suffix})" in taken:
        suffix += 1
    return f"{name} ({suffix})"


def _folder_subtree_ids(*, session: Session, user_id: int, root_id: int) -> set[int]:
    """The folder and all folders below it."""
    subtree = {root_id}
    frontier = {root_id}
    while frontier:
        children = session.exec(
            select(NoteFolders.id).where(
                NoteFolders.user_id == user_id, col(NoteFolders.parent_folder_id).in_(frontier)
            )
        ).all()
        frontier = {child for child in children if child is not None} - subtree
        subtree |= frontier
    return subtree


def move_note_to_folder(
    *, session: Session, current_user: User, note_id: int, folder_id: int | None
) -> Notes:
    user_id = _require_persisted_id(current_user.id, "User")
    _validate_folder_access(session=session, user_id=user_id, folder_id=folder_id)
    note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
    note.folder_id = folder_id
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def create_tag(*, session: Session, current_user: User, payload: TagCreate) -> NoteTags:
    user_id = _require_persisted_id(current_user.id, "User")
    existing = session.exec(
        select(NoteTags).where(
            NoteTags.user_id == current_user.id,
            NoteTags.name == payload.name,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")

    tag = NoteTags(
        user_id=user_id,
        name=payload.name,
        color=payload.color,
        description=payload.description,
    )
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


def assign_tags_to_note(
    *, session: Session, current_user: User, note_id: int, tag_ids: list[int]
) -> Notes:
    note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
    if not tag_ids:
        note.tags = []
        session.add(note)
        session.commit()
        session.refresh(note)
        return note

    tags = session.exec(
        select(NoteTags).where(
            NoteTags.user_id == current_user.id,
            col(NoteTags.id).in_(tag_ids),
        )
    ).all()
    if len(tags) != len(set(tag_ids)):
        raise HTTPException(status_code=400, detail="One or more tags are invalid")

    note.tags = list(tags)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def remove_tag_from_note(
    *, session: Session, current_user: User, note_id: int, tag_id: int
) -> Notes:
    note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
    note.tags = [tag for tag in note.tags if tag.id != tag_id]
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def link_notes(
    *,
    session: Session,
    current_user: User,
    source_note_id: int,
    target_note_ids: list[int],
) -> None:
    source_note = get_note_by_id(session=session, current_user=current_user, note_id=source_note_id)
    for target_note_id in set(target_note_ids):
        if source_note_id == target_note_id:
            continue
        target_note = get_note_by_id(
            session=session, current_user=current_user, note_id=target_note_id
        )
        existing = session.exec(
            select(NoteLinks).where(
                NoteLinks.source_note_id == source_note.id,
                NoteLinks.target_note_id == target_note.id,
            )
        ).first()
        if existing:
            continue
        session.add(NoteLinks(source_note_id=source_note.id, target_note_id=target_note.id))
    session.commit()


def sync_note_links(
    *,
    session: Session,
    current_user: User,
    source_note_id: int,
    target_note_ids: list[int],
) -> None:
    source_note = get_note_by_id(session=session, current_user=current_user, note_id=source_note_id)
    valid_target_ids = set(target_note_ids) - {source_note.id}

    for target_id in valid_target_ids:
        get_note_by_id(session=session, current_user=current_user, note_id=target_id)

    existing_links = session.exec(
        select(NoteLinks).where(NoteLinks.source_note_id == source_note.id)
    ).all()

    for link in existing_links:
        if link.target_note_id not in valid_target_ids:
            session.delete(link)

    for target_id in valid_target_ids:
        already_exists = any(link.target_note_id == target_id for link in existing_links)
        if not already_exists:
            session.add(NoteLinks(source_note_id=source_note.id, target_note_id=target_id))

    session.commit()


def sync_wiki_links(
    *, session: Session, current_user: User, source_note_id: int, content: str
) -> tuple[int, int]:
    """Synchronize Obsidian-style [[Note title]] links for one note."""
    source_note = get_note_by_id(session=session, current_user=current_user, note_id=source_note_id)
    requested_titles = {title.casefold() for title in extract_wiki_link_titles(content)}
    user_notes = session.exec(
        select(Notes).where(
            Notes.user_id == current_user.id,
            col(Notes.is_deleted).is_not(True),
        )
    ).all()
    target_ids = {
        note.id
        for note in user_notes
        if note.id != source_note.id and note.title.casefold() in requested_titles
    }

    existing_links = session.exec(
        select(NoteLinks).where(NoteLinks.source_note_id == source_note.id)
    ).all()
    referenced_links = [
        link for link in existing_links if link.link_type == NoteLinkType.referenced
    ]
    existing_pairs = {(link.source_note_id, link.target_note_id) for link in existing_links}
    removed = 0
    added = 0

    for link in referenced_links:
        if link.target_note_id not in target_ids:
            session.delete(link)
            removed += 1

    for target_id in target_ids:
        if (source_note.id, target_id) not in existing_pairs:
            session.add(
                NoteLinks(
                    source_note_id=source_note.id,
                    target_note_id=target_id,
                    link_type=NoteLinkType.referenced,
                )
            )
            added += 1

    if added or removed:
        session.commit()

    return added, removed


def rebuild_wiki_links(*, session: Session, current_user: User) -> tuple[int, int]:
    """Rebuild wiki-link edges for all active notes owned by a user."""
    notes = session.exec(
        select(Notes).where(
            Notes.user_id == current_user.id,
            col(Notes.is_deleted).is_not(True),
        )
    ).all()
    added = 0
    removed = 0
    for note in notes:
        note_added, note_removed = sync_wiki_links(
            session=session,
            current_user=current_user,
            source_note_id=_require_persisted_id(note.id, "Note"),
            content=note.content,
        )
        added += note_added
        removed += note_removed
    return added, removed


def link_note_to_document(
    *, session: Session, current_user: User, note_id: int, document_id: int | None
) -> Notes:
    user_id = _require_persisted_id(current_user.id, "User")
    _validate_document_access(session=session, user_id=user_id, document_id=document_id)
    note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)
    note.linked_document_id = document_id
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def get_note_graph(
    *, session: Session, current_user: User, note_id: int
) -> tuple[list[Notes], list[NoteLinks]]:
    """
    Get a note and all its connected notes (depth=1).
    Returns a tuple of (nodes, edges) for knowledge graph visualization.
    """
    # Get the center note
    center_note = get_note_by_id(session=session, current_user=current_user, note_id=note_id)

    # Get all outbound links (source_links) and inbound links (target_links)
    all_links = session.exec(
        select(NoteLinks).where(
            (NoteLinks.source_note_id == center_note.id)
            | (NoteLinks.target_note_id == center_note.id)
        )
    ).all()

    # Collect all connected note IDs
    connected_ids = {center_note.id}
    for link in all_links:
        connected_ids.add(link.source_note_id)
        connected_ids.add(link.target_note_id)

    # Get all connected notes
    nodes = session.exec(
        select(Notes).where(
            col(Notes.id).in_(connected_ids),
            Notes.user_id == current_user.id,
            col(Notes.is_deleted).is_not(True),
        )
    ).all()

    return list(nodes), list(all_links)


def get_full_user_graph(
    *, session: Session, current_user: User, limit: int = 500, offset: int = 0
) -> tuple[list[Notes], list[NoteLinks]]:
    """
    Get all notes and links for a user with pagination.
    Useful for building full knowledge graph visualization.
    """
    # Get all user notes (with limit/offset for pagination)
    nodes = session.exec(
        select(Notes)
        .where(
            Notes.user_id == current_user.id,
            col(Notes.is_deleted).is_not(True),
        )
        .order_by(col(Notes.updated_at).desc())
        .limit(limit)
        .offset(offset)
    ).all()

    node_ids = {node.id for node in nodes}

    # Get all links where both source and target are in the nodes list
    edges = session.exec(
        select(NoteLinks).where(
            col(NoteLinks.source_note_id).in_(node_ids),
            col(NoteLinks.target_note_id).in_(node_ids),
        )
    ).all()

    return list(nodes), list(edges)


def create_note_link(
    *,
    session: Session,
    current_user: User,
    source_note_id: int,
    target_note_id: int,
    link_type: str = "related",
    description: str | None = None,
) -> NoteLinks:
    """Create a link between two notes."""
    # Verify both notes belong to the user
    get_note_by_id(session=session, current_user=current_user, note_id=source_note_id)
    get_note_by_id(session=session, current_user=current_user, note_id=target_note_id)

    if source_note_id == target_note_id:
        raise HTTPException(status_code=400, detail="Cannot link a note to itself")

    # Check if link already exists
    existing = session.exec(
        select(NoteLinks).where(
            NoteLinks.source_note_id == source_note_id,
            NoteLinks.target_note_id == target_note_id,
        )
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Link already exists")

    link = NoteLinks(
        source_note_id=source_note_id,
        target_note_id=target_note_id,
        link_type=NoteLinkType(link_type),
        description=description,
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def delete_note_link(
    *, session: Session, current_user: User, source_note_id: int, target_note_id: int
) -> None:
    """Delete a link between two notes."""
    # Verify both notes belong to the user
    get_note_by_id(session=session, current_user=current_user, note_id=source_note_id)
    get_note_by_id(session=session, current_user=current_user, note_id=target_note_id)

    link = session.exec(
        select(NoteLinks).where(
            NoteLinks.source_note_id == source_note_id,
            NoteLinks.target_note_id == target_note_id,
        )
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    session.delete(link)
    session.commit()


def _validate_folder_access(*, session: Session, user_id: int, folder_id: int | None) -> None:
    if folder_id is None:
        return
    folder = session.exec(
        select(NoteFolders).where(
            NoteFolders.id == folder_id,
            NoteFolders.user_id == user_id,
            col(NoteFolders.is_deleted).is_not(True),
        )
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")


def _validate_document_access(*, session: Session, user_id: int, document_id: int | None) -> None:
    if document_id is None:
        return
    document = session.exec(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            col(Document.is_deleted).is_not(True),
        )
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Linked document not found")


def _create_version_snapshot(*, session: Session, note: Notes) -> Notes:
    snapshot = Notes(
        user_id=note.user_id,
        folder_id=note.folder_id,
        title=note.title,
        content=note.content,
        content_type=note.content_type,
        content_preview=note.content_preview,
        summary=note.summary,
        keywords=list(note.keywords or []),
        ai_generated=note.ai_generated,
        is_favorite=note.is_favorite,
        is_archived=True,
        is_pinned=note.is_pinned,
        color=note.color,
        emoji=note.emoji,
        linked_document_id=note.linked_document_id,
        linked_chat_session_id=note.linked_chat_session_id,
        parent_note_id=note.parent_note_id,
        version=note.version,
        previous_version_id=note.previous_version_id,
        is_public=note.is_public,
        is_locked=note.is_locked,
        is_deleted=True,
        locked_by=note.locked_by,
        locked_at=note.locked_at,
        word_count=note.word_count,
        char_count=note.char_count,
        read_time_minutes=note.read_time_minutes,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _should_snapshot(*, session: Session, note: Notes, update_data: dict[str, object]) -> bool:
    """Snapshot only real title/content edits, and at most once per interval."""
    changed = any(
        field_name in update_data and update_data[field_name] != getattr(note, field_name)
        for field_name in _VERSIONED_FIELDS
    )
    if not changed:
        return False
    if note.previous_version_id is None:
        return True
    previous = session.get(Notes, note.previous_version_id)
    if previous is None or previous.created_at is None:
        return True
    created_at = previous.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - created_at >= NOTE_VERSION_INTERVAL


def _prune_version_history(*, session: Session, note: Notes) -> None:
    """Drop snapshots beyond the retention limit from the end of the version chain."""
    kept = 0
    current: Notes = note
    while current.previous_version_id is not None:
        previous = session.get(Notes, current.previous_version_id)
        if previous is None:
            return
        if kept == NOTE_VERSION_RETENTION:
            current.previous_version_id = None
            session.add(current)
            session.flush()
            _delete_version_chain(session=session, snapshot=previous)
            return
        kept += 1
        current = previous


def _delete_version_chain(*, session: Session, snapshot: Notes) -> None:
    current: Notes | None = snapshot
    while current is not None:
        older_id = current.previous_version_id
        # Only snapshots (archived + deleted copies) are removed, never live notes
        if not (current.is_deleted and current.is_archived):
            return
        session.delete(current)
        session.flush()
        current = session.get(Notes, older_id) if older_id is not None else None


def _require_persisted_id(value: int | None, entity_name: str) -> int:
    if value is None:
        raise RuntimeError(f"{entity_name} must be persisted before use")
    return value
