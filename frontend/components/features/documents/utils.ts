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
      return "border-[#30d158] bg-[#30d158]/10 text-[#1f7a36]";
    case "processing":
      return "border-[#ff9f0a] bg-[#ff9f0a]/10 text-[#7d5206]";
    case "failed":
      return "border-[#ff3b30] bg-[#ff3b30]/10 text-[#a50011]";
    case "deleted":
      return "border-[rgba(15,0,0,0.18)] bg-accent text-muted-foreground";
    default:
      return "border-[rgba(15,0,0,0.18)] bg-accent text-muted-foreground";
  }
}

export function formatFileType(fileType: string) {
  if (!fileType) {
    return "Unknown";
  }

  const normalized = fileType.startsWith(".") ? fileType.slice(1) : fileType;
  return normalized.toUpperCase();
}
