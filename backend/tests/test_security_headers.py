from unittest import TestCase

from app.core.middleware import content_security_policy_for_path


class SecurityHeaderTests(TestCase):
    def test_regular_api_routes_keep_strict_same_origin_policy(self) -> None:
        policy = content_security_policy_for_path("/api/v1/notes")

        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("cdn.jsdelivr.net", policy)

    def test_swagger_allows_only_required_documentation_assets(self) -> None:
        policy = content_security_policy_for_path("/docs")

        self.assertIn("https://cdn.jsdelivr.net", policy)
        self.assertIn("'unsafe-inline'", policy)
        self.assertIn("frame-ancestors 'none'", policy)

    def test_redoc_allows_documentation_fonts(self) -> None:
        policy = content_security_policy_for_path("/redoc")

        self.assertIn("https://fonts.googleapis.com", policy)
        self.assertIn("https://fonts.gstatic.com", policy)
