"""Unit tests for SiteTrax client facility resolution and error taxonomy.

Run with: pytest backend/tests/test_client_mappings.py -v
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from app.data.sitetrax_client import (
    resolve_buckets,
    UnknownFacilityError,
    SiteTraxNotFoundError,
    SiteTraxAPIError,
    _request,
    get_last_asset,
    get_asset_timeline,
    get_video_metrics,
    project_metrics,
)


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """Keep retry tests fast while preserving retry call counts."""
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)


class TestResolveBuckets:
    """Test the ranked facility-name matching in resolve_buckets."""

    @patch("app.data.sitetrax_client.list_projects")
    def test_exact_match(self, mock_list):
        mock_list.return_value = [
            {"id": 1, "name": "Utah Intermodal Ramp"},
            {"id": 2, "name": "Norfolk Yard"},
        ]
        assert resolve_buckets("Utah Intermodal Ramp") == [1]

    @patch("app.data.sitetrax_client.list_projects")
    def test_prefix_match(self, mock_list):
        mock_list.return_value = [
            {"id": 1, "name": "Utah Intermodal Ramp"},
            {"id": 2, "name": "Utah Regional Terminal"},
        ]
        assert resolve_buckets("Utah") == [1, 2]

    @patch("app.data.sitetrax_client.list_projects")
    def test_token_match(self, mock_list):
        mock_list.return_value = [
            {"id": 1, "name": "Utah Intermodal Ramp"},
        ]
        assert resolve_buckets("Intermodal Ramp") == [1]

    @patch("app.data.sitetrax_client.list_projects")
    def test_substring_match(self, mock_list):
        mock_list.return_value = [
            {"id": 1, "name": "Utah Intermodal Ramp"},
        ]
        assert resolve_buckets("Intermodal") == [1]

    @patch("app.data.sitetrax_client.list_projects")
    def test_no_reverse_containment(self, mock_list):
        """"Ford" must NOT match "Norfolk" — reverse containment is disallowed."""
        mock_list.return_value = [
            {"id": 1, "name": "Norfolk Yard"},
        ]
        with pytest.raises(UnknownFacilityError) as exc:
            resolve_buckets("Ford")
        assert exc.value.facility == "Ford"
        assert "Norfolk Yard" in (exc.value.known_names or [])

    @patch("app.data.sitetrax_client.list_projects")
    def test_unknown_facility_raises(self, mock_list):
        mock_list.return_value = [
            {"id": 1, "name": "Utah Intermodal Ramp"},
        ]
        with pytest.raises(UnknownFacilityError) as exc:
            resolve_buckets("Nonexistent Facility")
        assert exc.value.facility == "Nonexistent Facility"
        assert "Utah Intermodal Ramp" in (exc.value.known_names or [])

    @patch("app.data.sitetrax_client.list_projects")
    def test_empty_input(self, mock_list):
        mock_list.return_value = [{"id": 1, "name": "Utah Intermodal Ramp"}]
        assert resolve_buckets("") == []
        assert resolve_buckets(None) == []

    @patch("app.data.sitetrax_client.list_projects")
    def test_dedup_preserves_order(self, mock_list):
        mock_list.return_value = [
            {"id": 1, "name": "Utah Intermodal Ramp"},
            {"id": 1, "name": "Utah Intermodal Ramp"},
        ]
        assert resolve_buckets("Utah Intermodal Ramp") == [1]


class TestErrorTaxonomy:
    """Test that _request raises the correct typed exceptions."""

    @patch("app.data.sitetrax_client.httpx.get")
    @patch("app.data.sitetrax_client._ensure_access_token")
    def test_404_raises_not_found(self, mock_ensure, mock_get):
        resp = MagicMock()
        resp.status_code = 404
        resp.text = "Not found"
        mock_get.return_value = resp
        with pytest.raises(SiteTraxNotFoundError):
            _request("/sv/assets/999/")

    @patch("app.data.sitetrax_client.httpx.get")
    @patch("app.data.sitetrax_client._ensure_access_token")
    def test_500_raises_api_error(self, mock_ensure, mock_get):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Server Error"
        mock_get.return_value = resp
        with pytest.raises(SiteTraxAPIError):
            _request("/sv/assets/")
        assert mock_get.call_count == 3

    @patch("app.data.sitetrax_client.httpx.get")
    @patch("app.data.sitetrax_client._ensure_access_token")
    def test_400_raises_api_error_no_retry(self, mock_ensure, mock_get):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "Bad Request"
        mock_get.return_value = resp
        with pytest.raises(SiteTraxAPIError):
            _request("/sv/assets/")
        assert mock_get.call_count == 1

    @patch("app.data.sitetrax_client.httpx.get")
    @patch("app.data.sitetrax_client._ensure_access_token")
    def test_timeout_raises_api_error(self, mock_ensure, mock_get):
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Request timed out")
        with pytest.raises(SiteTraxAPIError):
            _request("/sv/assets/")
        assert mock_get.call_count == 3

    @patch("app.data.sitetrax_client.httpx.get")
    @patch("app.data.sitetrax_client._ensure_access_token")
    def test_connect_error_raises_api_error(self, mock_ensure, mock_get):
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(SiteTraxAPIError):
            _request("/sv/assets/")
        assert mock_get.call_count == 3


class TestClientMappings:
    """Test endpoint-specific mapping fixes without live network calls."""

    @patch("app.data.sitetrax_client._request")
    def test_last_asset_unwraps_wrapper_and_project(self, mock_request):
        mock_request.return_value = {
            "asset": {"id": 10, "Text": "TRBU5341840", "bucket": {}},
            "project": {"id": 7, "name": "Utah Intermodal Ramp"},
        }
        result = get_last_asset()
        assert result["id"] == 10
        assert result["text"] == "TRBU5341840"
        assert result["facility"] == "Utah Intermodal Ramp"
        assert result["location"] == "Utah Intermodal Ramp"
        assert result["bucket_id"] == 7

    @patch("app.data.sitetrax_client._request")
    def test_last_asset_wrapper_with_null_asset_returns_none(self, mock_request):
        mock_request.return_value = {"asset": None, "project": {"id": 7, "name": "Utah Intermodal Ramp"}}
        assert get_last_asset() is None

    @patch("app.data.sitetrax_client._request")
    def test_video_metrics_returns_single_totals_dict(self, mock_request):
        mock_request.return_value = {
            "total_count": 12,
            "total_size": 3456,
            "total_length": 789,
        }
        result = get_video_metrics()
        assert result["total_count"] == 12
        assert result["total_size"] == 3456
        assert result["total_length"] == 789

    @patch("app.data.sitetrax_client._request")
    def test_project_metrics_joins_bucket_to_project_name(self, mock_request):
        mock_request.return_value = {
            "metrics": [
                {"created_at_day": "2026-06-01T00:00:00Z", "bucket": 7, "count": 5, "trans": 9},
            ],
            "projects": [
                {"id": 7, "name": "Utah Intermodal Ramp"},
            ],
        }
        rows = project_metrics()
        assert rows[0]["bucket_id"] == 7
        assert rows[0]["facility"] == "Utah Intermodal Ramp"
        assert rows[0]["project_name"] == "Utah Intermodal Ramp"

    @patch("app.data.sitetrax_client._request")
    def test_timeline_partial_search_retries_exact_text(self, mock_request):
        mock_request.side_effect = [
            {"results": []},
            {"results": [{"id": 1, "Text": "TRBU5341840", "created_at": "2026-06-01T01:00:00Z"}]},
            {"results": [{"id": 2, "Text": "TRBU5341840", "created_at": "2026-06-01T02:00:00Z"}]},
        ]
        rows = get_asset_timeline("trbu534")
        assert rows[0]["text"] == "TRBU5341840"
        assert rows[0]["partial_match"] is True
        assert rows[0]["requested_text"] == "TRBU534"
        assert rows[0]["matched_text"] == "TRBU5341840"

    def test_tool_guard_maps_unknown_facility_and_preserves_name(self):
        pytest.importorskip("google.adk")
        from app.agent import _tool_guard

        def needs_facility():
            """Docstring survives wraps."""
            raise UnknownFacilityError("Mars Yard", ["Utah Intermodal Ramp"])

        wrapped = _tool_guard(needs_facility)
        assert wrapped.__name__ == "needs_facility"
        assert "I don't recognize facility 'Mars Yard'" in wrapped()

    def test_query_assets_tool_returns_visualization_envelope(self, monkeypatch):
        pytest.importorskip("google.adk")
        import app.agent as agent

        monkeypatch.setattr(agent, "query_assets", lambda **_kwargs: [{
            "id": 1,
            "text": "TRDU1930583",
            "facility": "Utah Intermodal Ramp",
            "created_at": "2026-06-01T00:00:00Z",
            "asset_image": "https://example.test/image.jpg",
        }])

        payload = json.loads(agent.query_assets_tool(container_id="TRDU1930583"))
        assert payload["datasets"][0]["name"] == "assets"
        assert payload["datasets"][0]["rows"][0]["text"] == "TRDU1930583"
        assert any(viz["type"] == "table" for viz in payload["visualizations"])
        assert any(viz["type"] == "image_gallery" for viz in payload["visualizations"])

    def test_timeline_tool_returns_visualization_envelope(self, monkeypatch):
        pytest.importorskip("google.adk")
        import app.agent as agent

        monkeypatch.setattr(agent, "get_timeline_with_videos", lambda container_id, limit=20: [{
            "id": 1,
            "container_id": container_id,
            "facility": "Utah Intermodal Ramp",
            "datetime": "2026-06-01T00:00:00Z",
            "url": "https://example.test/video.mp4",
        }])

        payload = json.loads(agent.get_timeline_with_videos_tool("TRDU1930583"))
        assert payload["datasets"][0]["name"] == "asset_timeline"
        assert payload["timeline"][0]["container_id"] == "TRDU1930583"
        assert any(viz["type"] == "timeline" for viz in payload["visualizations"])
        assert any(viz["type"] == "video_gallery" for viz in payload["visualizations"])

    def test_mcp_timeline_returns_visualization_envelope(self, monkeypatch):
        pytest.importorskip("mcp")
        import app.mcp_server as mcp_server

        monkeypatch.setattr(mcp_server, "get_asset_timeline", lambda container_id: [{
            "id": 1,
            "text": container_id,
            "location": "Utah Intermodal Ramp",
            "datetime": "2026-06-01T00:00:00Z",
        }])

        payload = json.loads(mcp_server.sitetrax_asset_timeline("TRDU1930583", limit=5))
        assert payload["datasets"][0]["name"] == "asset_timeline"
        assert payload["timeline"][0]["text"] == "TRDU1930583"
        assert any(viz["type"] == "timeline" for viz in payload["visualizations"])
        assert not any(viz["type"] == "video_gallery" for viz in payload["visualizations"])

    def test_tool_response_normalizer_unwraps_mcp_content(self):
        from app.main import _coerce_tool_response_to_string

        wrapped = {
            "content": [{
                "type": "text",
                "text": json.dumps({"container_id": "TRDU1930583", "timeline": []}),
            }],
        }
        assert json.loads(_coerce_tool_response_to_string(wrapped))["container_id"] == "TRDU1930583"
