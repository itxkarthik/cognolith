export interface ApiError {
	status?: string;
	error?: string;
	detail?: string;
	message?: string;
	request_id?: string;
	details?: Array<{
		code: string;
		message: string;
		field?: string;
		value?: unknown;
	}>;
}

export interface MessageResponse {
	message: string;
}

export interface TokenResponse {
	access_token: string;
	refresh_token: string;
	token_type: string;
}

export interface LoginRequest {
	email: string;
	password: string;
}

export interface RegisterRequest {
	email: string;
	password: string;
	full_name?: string | null;
}

export interface VerificationChallenge {
	masked_email: string;
	expires_at: string;
	resend_available_at: string;
}

export interface ResendVerificationResponse {
	message: string;
	retry_after_seconds: number;
}

export interface User {
	id: number;
	email: string;
	is_active: boolean;
	is_superuser: boolean;
	is_verified: boolean;
	full_name?: string | null;
	created_at?: string | null;
}

export interface OllamaModelOption {
	name: string;
	size: number;
	modified_at?: string | null;
}

export interface UserAISettings {
	llm_model: string;
	embedding_model: string;
	ollama_available: boolean;
	available_models: OllamaModelOption[];
}

export interface FolderCreate {
	name: string;
	description?: string | null;
	parent_folder_id?: number | null;
	color?: string | null;
	icon?: string | null;
	emoji?: string | null;
}

export interface TagCreate {
	name: string;
	color?: string | null;
	description?: string | null;
}

export interface NoteFolder {
	id: number;
	user_id: number;
	name: string;
	description?: string | null;
	parent_folder_id?: number | null;
	color?: string | null;
	icon?: string | null;
	emoji?: string | null;
	created_at: string;
	updated_at: string;
}

export interface NoteTag {
	id: number;
	user_id: number;
	name: string;
	color?: string | null;
	description?: string | null;
	created_at: string;
}

export interface NoteTemplateData {
	id: string;
	name: string;
	description: string;
	content: string;
	tags: string[];
}

export interface NoteCreate {
	title: string;
	content: string;
	folder_id?: number | null;
	content_type?: string;
	keywords?: string[];
	tag_ids?: number[];
	linked_note_ids?: number[];
	is_favorite?: boolean;
	is_pinned?: boolean;
	linked_document_id?: number | null;
	linked_chat_session_id?: number | null;
}

export interface NoteUpdate {
	title?: string;
	content?: string;
	folder_id?: number | null;
	content_type?: string;
	keywords?: string[];
	tag_ids?: number[];
	linked_note_ids?: number[];
	is_favorite?: boolean;
	is_archived?: boolean;
	is_pinned?: boolean;
	linked_document_id?: number | null;
	linked_chat_session_id?: number | null;
}

export interface NoteResponse {
	id: number;
	user_id: number;
	folder_id?: number | null;
	title: string;
	content: string;
	content_type: string;
	summary?: string | null;
	keywords: string[];
	tag_ids: number[];
	linked_note_ids: number[];
	version: number;
	is_favorite: boolean;
	is_archived: boolean;
	is_pinned: boolean;
	is_deleted: boolean;
	linked_document_id?: number | null;
	linked_chat_session_id?: number | null;
	created_at: string;
	updated_at: string;
}

export interface NoteList {
	data: NoteResponse[];
	count: number;
}

export interface DocumentCreate {
	title: string;
	tags?: string[];
	language?: string;
}

export interface DocumentUpdate {
	title?: string;
	summary?: string | null;
	tags?: string[];
	keywords?: string[];
	language?: string;
}

export interface DocumentResponse {
	id: number;
	user_id: number;
	title: string;
	file_name: string;
	file_path: string;
	file_size: number;
	file_type: string;
	mime_type: string;
	status: string;
	language: string;
	tags: string[];
	keywords: string[];
	summary?: string | null;
	content_preview?: string | null;
	chunk_count: number;
	word_count?: number | null;
	page_count?: number | null;
	processing_error?: string | null;
	is_deleted: boolean;
	created_at: string;
	updated_at: string;
}

export interface DocumentContentResponse {
	id: number;
	title: string;
	status: string;
	content: string;
	updated_at: string;
}

export interface DocumentList {
	data: DocumentResponse[];
	count: number;
}

export type ChatRole = "user" | "assistant" | "system";

export interface ChatCreate {
	title?: string | null;
	description?: string | null;
}

export interface ChatMessageCreate {
	content: string;
	role?: ChatRole;
}

export interface ChatSourceDocument {
	document_id: number;
	title: string;
	chunk_count: number;
	max_score: number | null;
	citation_ids: number[];
	origin: "vector" | "inventory" | "lexical" | "hybrid";
}

export interface ChatSourceChunk {
	chunk_id: number;
	document_id: number;
	document_title: string;
	chunk_index: number;
	chunk_end_index?: number | null;
	score: number | null;
	hybrid_score?: number | null;
	preview: string;
	citation_id?: number | null;
	origin: "vector" | "inventory" | "lexical" | "hybrid";
}

export interface ChatSourceNote {
	note_id: number;
	title: string;
	score: number | null;
	hybrid_score?: number | null;
	preview: string;
	citation_id?: number | null;
	origin: "vector" | "inventory" | "lexical" | "hybrid";
}

export interface ChatSources {
	documents: ChatSourceDocument[];
	chunks: ChatSourceChunk[];
	notes: ChatSourceNote[];
}

export interface ChatMessageResponse {
	id: number;
	session_id: number;
	role: ChatRole;
	content: string;
	model_used?: string | null;
	tokens_used?: number | null;
	response_time_ms?: number | null;
	sources?: ChatSources | null;
	created_at: string;
	updated_at: string;
}

export interface ChatResponse {
	id: number;
	user_id: number;
	title?: string | null;
	description?: string | null;
	is_archived: boolean;
	is_pinned: boolean;
	last_message_at: string;
	created_at: string;
	updated_at: string;
	messages: ChatMessageResponse[];
}

export interface ChatSessionList {
	data: ChatResponse[];
	count: number;
}

export interface SearchFilters {
	entity_types?: Array<"document" | "note" | "chat">;
	tags?: string[];
	folder_id?: number;
	date_from?: string;
	date_to?: string;
}

export interface SearchQuery {
	query: string;
	filters?: SearchFilters;
	page?: number;
	page_size?: number;
}

export interface SearchResultItem {
	id: number;
	entity_type: "document" | "note" | "chat";
	title?: string | null;
	snippet?: string | null;
	score?: number | null;
	created_at?: string | null;
	updated_at?: string | null;
}

export interface SearchResponse {
	query: string;
	results: SearchResultItem[];
	total: number;
	page: number;
	page_size: number;
	filters?: SearchFilters;
}
