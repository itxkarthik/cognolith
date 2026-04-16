"""
Comprehensive validation utilities for input sanitization and validation.

This module provides reusable validators for Pydantic models to ensure:
- XSS prevention through HTML/text sanitization
- SQL injection prevention through parameterized queries (handled by ORM)
- Email format validation
- URL validation
- String length limits
- Pattern matching for specific fields
"""

import re
from typing import Any
from urllib.parse import urlparse
import html

from pydantic import field_validator, ValidationError


# Regex patterns for validation
EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
URL_REGEX = r"^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)$"
PHONE_REGEX = r"^\+?1?\d{9,15}$"
SLUG_REGEX = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
HEX_COLOR_REGEX = r"^#(?:[0-9a-fA-F]{3}){1,2}$"


def validate_email(email: str | None) -> str | None:
    """
    Validate email format.
    
    Args:
        email: Email address to validate
        
    Returns:
        Validated email or None
        
    Raises:
        ValueError: If email format is invalid
    """
    if email is None:
        return None
    
    email = email.strip().lower()
    if not re.match(EMAIL_REGEX, email):
        raise ValueError(f"Invalid email format: {email}")
    
    if len(email) > 254:  # RFC 5321
        raise ValueError("Email address too long (max 254 characters)")
    
    return email


def validate_url(url: str | None) -> str | None:
    """
    Validate URL format and protocol.
    
    Args:
        url: URL to validate
        
    Returns:
        Validated URL or None
        
    Raises:
        ValueError: If URL format is invalid
    """
    if url is None:
        return None
    
    url = url.strip()
    
    try:
        result = urlparse(url)
        # Check for valid protocol
        if result.scheme not in ('http', 'https', 'ftp', 'ftps'):
            raise ValueError(f"Invalid URL protocol: {result.scheme}")
        # Check for netloc (domain)
        if not result.netloc:
            raise ValueError("URL must include domain")
        return url
    except Exception as e:
        raise ValueError(f"Invalid URL format: {str(e)}")


def validate_phone(phone: str | None) -> str | None:
    """
    Validate phone number format.
    
    Args:
        phone: Phone number to validate
        
    Returns:
        Validated phone or None
        
    Raises:
        ValueError: If phone format is invalid
    """
    if phone is None:
        return None
    
    # Remove common separators
    phone = re.sub(r"[\s\-\(\)\+.]", "", phone)
    
    if not re.match(PHONE_REGEX, phone):
        raise ValueError(f"Invalid phone format: {phone}")
    
    return phone


def validate_slug(slug: str | None) -> str | None:
    """
    Validate slug format (lowercase letters, numbers, hyphens only).
    
    Args:
        slug: Slug to validate
        
    Returns:
        Validated slug or None
        
    Raises:
        ValueError: If slug format is invalid
    """
    if slug is None:
        return None
    
    slug = slug.strip().lower()
    
    if not re.match(SLUG_REGEX, slug):
        raise ValueError(f"Invalid slug format: {slug}")
    
    if len(slug) > 100:
        raise ValueError("Slug too long (max 100 characters)")
    
    return slug


def validate_hex_color(color: str | None) -> str | None:
    """
    Validate hex color format.
    
    Args:
        color: Hex color to validate (e.g., #FFFFFF)
        
    Returns:
        Validated color or None
        
    Raises:
        ValueError: If color format is invalid
    """
    if color is None:
        return None
    
    color = color.strip()
    
    if not re.match(HEX_COLOR_REGEX, color):
        raise ValueError(f"Invalid hex color format: {color}")
    
    return color.lower()


def validate_string_length(value: str | None, min_length: int = 0, max_length: int = 10000) -> str | None:
    """
    Validate string length.
    
    Args:
        value: String to validate
        min_length: Minimum length
        max_length: Maximum length
        
    Returns:
        Validated string or None
        
    Raises:
        ValueError: If string length is invalid
    """
    if value is None:
        return None
    
    if len(value) < min_length:
        raise ValueError(f"String too short (min {min_length} characters)")
    
    if len(value) > max_length:
        raise ValueError(f"String too long (max {max_length} characters)")
    
    return value


def sanitize_html_content(content: str | None) -> str | None:
    """
    Sanitize HTML content to prevent XSS.
    
    This removes or escapes potentially dangerous HTML/JavaScript.
    
    Args:
        content: HTML content to sanitize
        
    Returns:
        Sanitized content or None
    """
    if content is None:
        return None
    
    # Remove script tags and content
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove event handlers
    content = re.sub(r' on[a-z]+\s*=\s*["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
    content = re.sub(r' on[a-z]+\s*=\s*[^\s>]*', '', content, flags=re.IGNORECASE)
    
    # Remove iframe tags
    content = re.sub(r'<iframe[^>]*>.*?</iframe>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove potentially dangerous tags
    dangerous_tags = ['object', 'embed', 'applet', 'meta', 'link', 'style']
    for tag in dangerous_tags:
        content = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(f'<{tag}[^>]*/?>', '', content, flags=re.IGNORECASE)
    
    return content.strip()


def sanitize_plain_text(text: str | None) -> str | None:
    """
    Sanitize plain text to prevent injection attacks.
    
    This escapes HTML entities and removes control characters.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text or None
    """
    if text is None:
        return None
    
    # Escape HTML entities
    text = html.escape(text)
    
    # Remove control characters (except newlines and tabs)
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t\r')
    
    return text.strip()


def validate_no_xss(value: str | None) -> str | None:
    """
    Validate that string doesn't contain XSS patterns.
    
    Args:
        value: Value to check
        
    Returns:
        Validated value or None
        
    Raises:
        ValueError: If potential XSS detected
    """
    if value is None:
        return None
    
    # Check for common XSS patterns
    xss_patterns = [
        r'<\s*script[^>]*>',
        r'javascript\s*:',
        r'on[a-z]+\s*=',
        r'<\s*iframe',
        r'<\s*object',
        r'<\s*embed',
    ]
    
    value_lower = value.lower()
    for pattern in xss_patterns:
        if re.search(pattern, value_lower, re.IGNORECASE):
            raise ValueError("Potential XSS attack detected in input")
    
    return value


def validate_no_sql_injection(value: str | None) -> str | None:
    """
    Validate that string doesn't contain SQL injection patterns.
    Note: The primary defense is parameterized queries in the ORM.
    This is a secondary defense check.
    
    Args:
        value: Value to check
        
    Returns:
        Validated value or None
        
    Raises:
        ValueError: If potential SQL injection detected
    """
    if value is None:
        return None
    
    # Check for common SQL injection patterns
    sql_patterns = [
        r"('\s*(OR|AND)\s*'1'\s*=\s*'1)",  # Classic SQL injection
        r"(;\s*DROP\s+TABLE)",
        r"(UNION\s+SELECT)",
        r"(\/\*.*\*\/)",  # SQL comments
        r"(--\s*\n)",
        r"(xp_|sp_)",  # SQL Server extended procedures
    ]
    
    value_upper = value.upper()
    for pattern in sql_patterns:
        if re.search(pattern, value_upper):
            raise ValueError("Potential SQL injection detected in input")
    
    return value


# Pydantic field validators (ready to use in models)

def validate_email_field(value: str | None) -> str | None:
    """Field validator for email fields."""
    return validate_email(value)


def validate_url_field(value: str | None) -> str | None:
    """Field validator for URL fields."""
    return validate_url(value)


def validate_hex_color_field(value: str | None) -> str | None:
    """Field validator for hex color fields."""
    return validate_hex_color(value)


def validate_no_xss_field(value: str | None) -> str | None:
    """Field validator to prevent XSS."""
    if value is not None:
        validate_no_xss(value)
    return value


def validate_no_sql_injection_field(value: str | None) -> str | None:
    """Field validator to prevent SQL injection."""
    if value is not None:
        validate_no_sql_injection(value)
    return value
