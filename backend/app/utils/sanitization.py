import bleach

# Tags and attributes safe for rich-text note content (Markdown rendered to HTML)
ALLOWED_TAGS = [
    "a",
    "abbr",
    "acronym",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
    "img",
    "span",
    "div",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "abbr": ["title"],
    "acronym": ["title"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "*": ["class"],
}

# Only allow safe URL schemes
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(value: str) -> str:
    """Sanitize rich-text HTML: strip dangerous tags/attributes, keep safe ones."""
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


def strip_all_html(value: str) -> str:
    """Remove ALL HTML tags — use for plain-text fields like titles and names."""
    return bleach.clean(value, tags=[], attributes={}, strip=True).strip()


def sanitize_plain_text(value: str) -> str:
    """Strip HTML and collapse excessive whitespace for plain-text inputs."""
    cleaned = strip_all_html(value)
    # Collapse multiple spaces/newlines into single space
    return " ".join(cleaned.split())
