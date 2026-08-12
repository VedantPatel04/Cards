from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class PublicSchemaDocsTests(APITestCase):
    def test_schema_and_docs_are_public(self):
        schema = self.client.get(reverse("schema"))
        self.assertEqual(schema.status_code, status.HTTP_200_OK)
        self.assertIn(b"openapi", schema.content[:200].lower())

        docs = self.client.get(reverse("swagger-ui"))
        self.assertEqual(docs.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=False)
    def test_docs_remain_public_when_debug_is_false(self):
        """Docs must not be gated on DEBUG — portfolio/Render need them live."""
        self.assertEqual(
            self.client.get(reverse("swagger-ui")).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(reverse("schema")).status_code,
            status.HTTP_200_OK,
        )

    def test_schema_includes_core_paths_and_jwt(self):
        from drf_spectacular.generators import SchemaGenerator

        schema = SchemaGenerator().get_schema(request=None, public=True)
        paths = schema["paths"]
        for path in (
            "/api/register/",
            "/api/token/",
            "/api/wallet/",
            "/api/upload/",
            "/api/recommendations/",
        ):
            self.assertIn(path, paths)
        self.assertIn("jwtAuth", schema["components"]["securitySchemes"])
        # Try it out needs a documented multipart body for uploads.
        upload_post = paths["/api/upload/"]["post"]
        self.assertIn("requestBody", upload_post)
