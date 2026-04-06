import { apiClient } from "@/lib/api/client";
import type { SearchResponse } from "@/types";

export type SearchEntityType = "document" | "note" | "chat";

export interface GlobalSearchParams {
	query: string;
	entityTypes?: SearchEntityType[];
	folderId?: number;
	dateFrom?: string;
	dateTo?: string;
	page?: number;
	pageSize?: number;
}

export async function globalSearch(params: GlobalSearchParams): Promise<SearchResponse> {
	const queryParams: Record<string, string | number> = {
		query: params.query,
		page: params.page ?? 1,
		page_size: params.pageSize ?? 20,
	};

	if (params.entityTypes && params.entityTypes.length > 0) {
		queryParams.entity_types = params.entityTypes.join(",");
	}

	if (params.folderId !== undefined) {
		queryParams.folder_id = params.folderId;
	}

	if (params.dateFrom) {
		queryParams.date_from = params.dateFrom;
	}

	if (params.dateTo) {
		queryParams.date_to = params.dateTo;
	}

	const response = await apiClient.get<SearchResponse>("/search/", {
		params: queryParams,
	});

	return response.data;
}
