from __future__ import annotations

import unittest

from web.app import app, config, health, providers
from web.schemas import (
    AppConfigResponse,
    HealthResponse,
    JobsResponse,
    ProvidersResponse,
    SearchResultResponse,
    SessionDetailResponse,
    SessionPageResponse,
)


class WebResponseSchemaTests(unittest.TestCase):
    def test_main_rest_routes_publish_response_models_in_openapi(self) -> None:
        paths = app.openapi()["paths"]
        expected = {
            ("get", "/api/config"): "AppConfigResponse",
            ("get", "/api/providers"): "ProvidersResponse",
            ("get", "/api/sessions"): "SessionPageResponse",
            ("get", "/api/sessions/{session_id}"): "SessionDetailResponse",
            ("get", "/api/jobs"): "JobsResponse",
            ("post", "/api/import"): "JobResponse",
            ("post", "/api/search/start"): "SearchResultResponse",
        }
        for (method, path), schema_name in expected.items():
            with self.subTest(method=method, path=path):
                response_schema = paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]
                self.assertEqual(response_schema["$ref"], f"#/components/schemas/{schema_name}")


    def test_live_config_and_provider_metadata_match_declared_dtos(self) -> None:
        self.assertTrue(HealthResponse.model_validate(health()).ok)
        self.assertTrue(AppConfigResponse.model_validate(config()).formats)
        provider_response = ProvidersResponse.model_validate(providers())
        self.assertGreater(len(provider_response.providers), 0)

    def test_provider_response_preserves_plugin_extension_fields(self) -> None:
        payload = {
            "providers": [{
                "id": "third-party",
                "name": "Third party",
                "task": "generation",
                "description": "Provider plugin",
                "execution": "remote",
                "ready": True,
                "message": "Ready",
                "vendor_metadata": {"region": "eu"},
            }],
        }
        response = ProvidersResponse.model_validate(payload)
        self.assertEqual(response.providers[0].model_extra["vendor_metadata"], {"region": "eu"})

    def test_session_and_job_contracts_validate_expected_shapes(self) -> None:
        session = {
            "id": "2026-10-17_10-30-00",
            "title": "Réunion",
            "started_at": None,
            "summary_excerpt": "Notes",
            "summary": True,
            "transcript": True,
            "audio": False,
            "audio_tracks": [],
            "duration_seconds": None,
            "has_metadata": True,
            "processing": None,
            "metadata": {"title_source": "user"},
            "summary_translations": ["en"],
            "files": {"summary": True, "transcript": True, "audio_tracks": [], "analysis": False},
        }
        detail = SessionDetailResponse.model_validate(session)
        self.assertEqual(detail.metadata["title_source"], "user")
        page = SessionPageResponse.model_validate({
            "items": [{key: session[key] for key in (
                "id", "title", "started_at", "summary_excerpt", "summary", "transcript",
                "audio", "audio_tracks", "duration_seconds", "has_metadata", "processing",
            )}],
            "count": 1, "page_count": 1, "limit": "all", "offset": 0,
            "root": "seances", "root_exists": True, "project_root": ".",
        })
        self.assertEqual(page.items[0].id, detail.id)

        jobs = JobsResponse.model_validate({
            "items": [{"id": "job-1", "kind": "process", "state": "queued", "phase": "queued"}],
            "active": None,
            "queue": {"waiting": 1, "running": None, "serial": True},
        })
        self.assertEqual(jobs.queue.waiting, 1)

    def test_search_response_requires_progress_and_source_contract(self) -> None:
        response = SearchResultResponse.model_validate({
            "id": "search-1",
            "state": "running",
            "message": "Recherche en cours",
            "query": "contrat",
            "session_ids": [],
            "sessions_total": 0,
            "sessions_scanned": 0,
            "passages_found": 0,
            "answer": None,
            "llm_error": None,
            "sources": [{
                "source_number": 1, "source_id": "source-1", "included": True,
                "citation_number": 1, "title": "Titre", "session_id": "session-1",
                "filename": "resume.md", "kind": "summary", "text": "Extrait",
            }],
            "created_at": None,
            "updated_at": None,
            "finished_at": None,
        })
        self.assertEqual(response.sources[0].source_id, "source-1")


if __name__ == "__main__":
    unittest.main()
