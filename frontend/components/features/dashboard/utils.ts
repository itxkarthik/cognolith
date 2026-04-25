export function formatDate(value: string) {
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) {
		return "Unknown date";
	}

	return new Intl.DateTimeFormat("en-US", {
		month: "short",
		day: "2-digit",
		year: "numeric",
	}).format(date);
}

export function formatBytes(bytes: number) {
	if (!Number.isFinite(bytes) || bytes < 0) {
		return "-";
	}

	if (bytes < 1024) {
		return `${bytes} B`;
	}

	const kb = bytes / 1024;
	if (kb < 1024) {
		return `${kb.toFixed(1)} KB`;
	}

	const mb = kb / 1024;
	return `${mb.toFixed(1)} MB`;
}

export function extractPreview(content: string, maxLength = 110) {
	const trimmed = content.replace(/\s+/g, " ").trim();
	if (!trimmed) {
		return "No content preview available yet.";
	}

	if (trimmed.length <= maxLength) {
		return trimmed;
	}

	return `${trimmed.slice(0, maxLength - 1)}...`;
}
