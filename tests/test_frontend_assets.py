"""Verify frontend asset URLs through the application's HTTP routes."""

from html.parser import HTMLParser
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.main import FRONTEND_DIR, app


class AssetLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.urls.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.urls.append(attrs["href"])


def test_frontend_assets_are_served_from_organized_folders():
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        links = AssetLinks()
        links.feed(page.text)
        assert links.urls
        referenced = set()
        for url in links.urls:
            path = urlsplit(url).path.lstrip("/")
            referenced.add(path)
            assert path.startswith(("css/", "js/")), url
            response = client.get("/" + url)
            assert response.status_code == 200, url
            assert response.content == (FRONTEND_DIR / path).read_bytes(), url
            mime = "text/css" if path.endswith(".css") else "javascript"
            assert mime in response.headers["content-type"], url
        expected = {
            path.relative_to(FRONTEND_DIR).as_posix()
            for folder, pattern in (("css", "*.css"), ("js", "*.js"))
            for path in (FRONTEND_DIR / folder).glob(pattern)
        }
        assert referenced == expected


def test_missing_frontend_asset_returns_404():
    with TestClient(app) as client:
        for url in ("/css/missing.css", "/js/missing.js"):
            assert client.get(url).status_code == 404
