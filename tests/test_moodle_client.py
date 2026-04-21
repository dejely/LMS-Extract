from pathlib import Path

import httpx

from lms_extrafiliator.config import Settings
from lms_extrafiliator.moodle import MoodleClient


def test_http_login_and_course_discovery() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/login/index.php":
            return httpx.Response(200, text='<input name="logintoken" value="token">')
        if request.method == "POST" and request.url.path == "/login/index.php":
            return httpx.Response(200, text='<a href="/login/logout.php">Logout</a>')
        if request.url.path == "/my/courses.php":
            return httpx.Response(200, text='<a href="/course/view.php?id=12">History</a>')
        return httpx.Response(200, text="")

    settings = Settings(
        base_url="https://lms.test",
        username="user",
        password="pass",
        download_dir=Path("downloads"),
        auth_mode="http",
        login_path=None,
        state_dir=Path(".lms-extract"),
    )
    with MoodleClient(settings, transport=httpx.MockTransport(handler)) as client:
        client.authenticate()
        courses = client.discover_courses()

    assert len(courses) == 1
    assert courses[0].id == "12"


def test_resource_page_resolves_to_pluginfile() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/mod/resource/view.php":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<a href="/pluginfile.php/1/mod_resource/content/0/file.pdf">Download</a>',
            )
        if request.url.path.startswith("/pluginfile.php"):
            return httpx.Response(
                200,
                headers={"content-type": "application/pdf", "content-length": "3"},
                content=b"abc",
            )
        return httpx.Response(404)

    settings = Settings(
        base_url="https://lms.test",
        username="user",
        password="pass",
        download_dir=Path("downloads"),
        auth_mode="http",
        login_path=None,
        state_dir=Path(".lms-extract"),
    )
    from lms_extrafiliator.models import Resource

    resource = Resource(
        course_id="12",
        course_name="History",
        topic="Week 1",
        title="File",
        url="https://lms.test/mod/resource/view.php?id=1",
        source_url="https://lms.test/course/view.php?id=12",
    )
    with MoodleClient(settings, transport=httpx.MockTransport(handler)) as client:
        prepared = client.prepare_download(resource)

    assert prepared.final_url.endswith("/pluginfile.php/1/mod_resource/content/0/file.pdf")
    assert prepared.filename == "file.pdf"
    assert prepared.size == 3


def test_http_login_can_use_upv_style_login_php() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.method == "GET" and request.url.path == "/login.php":
            return httpx.Response(
                200,
                text='<form action="login.php"><input name="username"><input name="password"></form>',
            )
        if request.method == "POST" and request.url.path == "/login.php":
            return httpx.Response(200, text='<a href="/login/logout.php">Logout</a>')
        return httpx.Response(404)

    settings = Settings(
        base_url="https://lms.upvisayas.net",
        username="user",
        password="pass",
        download_dir=Path("downloads"),
        auth_mode="http",
        login_path="login.php",
        state_dir=Path(".lms-extract"),
    )
    with MoodleClient(settings, transport=httpx.MockTransport(handler)) as client:
        client.authenticate()

    assert requested_paths == ["/login.php", "/login.php"]


def test_http_login_auto_detects_login_php_after_missing_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/login/index.php":
            return httpx.Response(404)
        if request.method == "GET" and request.url.path == "/login.php":
            return httpx.Response(
                200,
                text='<form action="login.php"><input name="username"><input name="password"></form>',
            )
        if request.method == "POST" and request.url.path == "/login.php":
            return httpx.Response(200, text='<a href="/login/logout.php">Logout</a>')
        return httpx.Response(404)

    settings = Settings(
        base_url="https://lms.upvisayas.net",
        username="user",
        password="pass",
        download_dir=Path("downloads"),
        auth_mode="http",
        login_path=None,
        state_dir=Path(".lms-extract"),
    )
    with MoodleClient(settings, transport=httpx.MockTransport(handler)) as client:
        client.authenticate()
