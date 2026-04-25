export function formatDate(value: string) {
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) {
		return "Unknown date";
	}

	return new Intl.DateTimeFormat("en-US", {
		month: "short",
		day: "2-digit",
		year: "numeric",
		hour: "2-digit",
		minute: "2-digit",
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
	if (mb < 1024) {
		return `${mb.toFixed(1)} MB`;
	}

	const gb = mb / 1024;
	return `${gb.toFixed(1)} GB`;
}

export function getStatusClasses(status: string) {
	switch (status.toLowerCase()) {
		case "completed":
			return "border-emerald-700/60 bg-emerald-900/20 text-emerald-300";
		case "processing":
			return "border-amber-700/60 bg-amber-900/20 text-amber-300";
		case "failed":
			return "border-rose-700/60 bg-rose-900/20 text-rose-300";
		case "deleted":
			return "border-zinc-700/60 bg-zinc-900/20 text-zinc-300";
		default:
			return "border-zinc-700/60 bg-zinc-900/20 text-zinc-300";
	}
}

export function formatFileType(fileType: string) {
	if (!fileType) {
		return "Unknown";
	}

	const normalized = fileType.startsWith(".") ? fileType.slice(1) : fileType;
	return normalized.toUpperCase();
}
