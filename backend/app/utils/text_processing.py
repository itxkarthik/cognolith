import re


def clean_text(content: str) -> str:
	normalized = content.replace("\r\n", "\n").replace("\r", "\n")
	normalized = re.sub(r"[ \t]+", " ", normalized)
	normalized = re.sub(r"\n{3,}", "\n\n", normalized)
	return normalized.strip()


def create_content_preview(content: str, max_length: int = 500) -> str:
	text = clean_text(content)
	if len(text) <= max_length:
		return text
	return text[: max_length - 3].rstrip() + "..."


def split_text_into_chunks(content: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
	if chunk_size <= 0:
		raise ValueError("chunk_size must be greater than 0")
	if overlap < 0:
		raise ValueError("overlap must be greater than or equal to 0")
	if overlap >= chunk_size:
		raise ValueError("overlap must be less than chunk_size")

	text = clean_text(content)
	if not text:
		return []

	chunks: list[str] = []
	step = chunk_size - overlap
	start = 0
	while start < len(text):
		chunk = text[start : start + chunk_size].strip()
		if chunk:
			chunks.append(chunk)
		start += step
	return chunks
