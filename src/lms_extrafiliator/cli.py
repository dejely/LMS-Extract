from __future__ import annotations

from collections import defaultdict
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from .browser_auth import capture_browser_session
from .config import load_config
from .course_names import base_course_key, display_course_key, is_lecture_course
from .downloader import download_resources
from .errors import LMSExtractError
from .models import Course, Resource, Topic
from .moodle import MoodleClient
from .utils import collapse_whitespace

app = typer.Typer(no_args_is_help=True, help="Download authorized files from Moodle-style LMS sites.")
auth_app = typer.Typer(no_args_is_help=True, help="Authentication helpers.")
app.add_typer(auth_app, name="auth")
console = Console()


@app.command()
def courses() -> None:
    """List discovered Moodle courses."""
    try:
        settings = load_config()
        with MoodleClient(settings) as client:
            client.authenticate()
            discovered = client.discover_courses()
        _print_courses(discovered)
    except LMSExtractError as exc:
        _fail(str(exc))


@app.command()
def topics(
    course: str = typer.Option(..., "--course", help='Moodle course ID or course key, such as "CMSC 126".')
) -> None:
    """List topics and downloadable resource counts in one course."""
    try:
        settings = load_config()
        with MoodleClient(settings) as client:
            client.authenticate()
            target = _target_courses(client, all_courses=False, course=course)[0]
            course_topics = client.get_course_topics(target.id, target.name or None)
        _print_topics(course_topics)
    except LMSExtractError as exc:
        _fail(str(exc))


@app.command("dry-run")
def dry_run(
    academic_year: Optional[str] = typer.Argument(None, help='Optional academic year for --all, such as "25-26".'),
    all_courses: bool = typer.Option(False, "--all", help="Preview all discovered courses."),
    course: Optional[str] = typer.Option(None, "--course", help='Preview one Moodle course ID or key, such as "CMSC 126".'),
    topic: Optional[str] = typer.Option(None, "--topic", help="Limit to one topic name."),
) -> None:
    """Preview the files that would be downloaded."""
    _run_download(all_courses=all_courses, course=course, topic=topic, academic_year=academic_year, dry=True)


@app.command()
def download(
    academic_year: Optional[str] = typer.Argument(None, help='Optional academic year for --all, such as "25-26".'),
    all_courses: bool = typer.Option(False, "--all", help="Download all discovered courses."),
    course: Optional[str] = typer.Option(None, "--course", help='Download one Moodle course ID or key, such as "CMSC 126".'),
    topic: Optional[str] = typer.Option(None, "--topic", help="Limit to one topic name."),
) -> None:
    """Download files into DOWNLOAD_DIR/course/topic folders."""
    _run_download(all_courses=all_courses, course=course, topic=topic, academic_year=academic_year, dry=False)


@auth_app.command("browser")
def auth_browser() -> None:
    """Capture browser cookies for SSO/MFA Moodle sites."""
    try:
        settings = load_config(require_credentials=False)
        path = capture_browser_session(settings)
        console.print(f"[green]Saved browser session:[/green] {path}")
        console.print("Set LMS_AUTH_MODE=browser in .env to reuse it.")
    except LMSExtractError as exc:
        _fail(str(exc))


def _run_download(
    *,
    all_courses: bool,
    course: str | None,
    topic: str | None,
    academic_year: str | None,
    dry: bool,
) -> None:
    if all_courses == bool(course):
        _fail('Choose exactly one target: --all or --course "COURSE KEY".')
    if topic and not course:
        _fail("--topic can only be used with --course.")
    if academic_year and not all_courses:
        _fail('Academic year filtering only works with --all, for example: download --all "25-26".')

    try:
        settings = load_config()
        with MoodleClient(settings) as client:
            client.authenticate()
            target_courses = _target_courses(client, all_courses=all_courses, course=course, academic_year=academic_year)
            resources = _collect_resources(client, target_courses, topic)
            if not resources:
                console.print("[yellow]No downloadable resources found.[/yellow]")
                return
            results = download_resources(settings, client, resources, dry_run=dry)
        _print_download_results(results, dry=dry)
    except LMSExtractError as exc:
        _fail(str(exc))


def _target_courses(
    client: MoodleClient,
    *,
    all_courses: bool,
    course: str | None,
    academic_year: str | None = None,
) -> list[Course]:
    if course:
        return [_resolve_course(client, course)]
    courses = client.discover_courses()
    if academic_year:
        courses = _filter_courses_by_academic_year(courses, academic_year)
        if not courses:
            raise LMSExtractError(f"No discovered courses matched academic year '{academic_year}'.")
    return courses


def _filter_courses_by_academic_year(courses: list[Course], academic_year: str) -> list[Course]:
    tokens = _academic_year_tokens(academic_year)
    return [
        course
        for course in courses
        if any(token in _normalize_year_text(course.name) for token in tokens)
    ]


def _academic_year_tokens(academic_year: str) -> set[str]:
    normalized = _normalize_year_text(academic_year)
    numbers = [part for part in normalized.split("-") if part]
    tokens = {normalized}

    if len(numbers) >= 2:
        start, end = numbers[0], numbers[1]
        start_short = start[-2:]
        end_short = end[-2:]
        start_long = f"20{start_short}" if len(start) == 2 else start
        end_long = f"20{end_short}" if len(end) == 2 else end
        tokens.update(
            {
                f"{start_short}-{end_short}",
                f"{start_long}-{end_short}",
                f"{start_long}-{end_long}",
            }
        )

    return tokens


def _normalize_year_text(value: str) -> str:
    chars: list[str] = []
    for char in value.casefold():
        if char.isdigit() or char == "-":
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-")


def _resolve_course(client: MoodleClient, course_query: str) -> Course:
    query = collapse_whitespace(course_query)
    discovered = client.discover_courses()

    for course in discovered:
        if course.id == query:
            return course

    course_keys = _course_keys(discovered)
    normalized_query = _normalize_course_key(query)
    matches = [course for course in discovered if _normalize_course_key(course_keys[course.id]) == normalized_query]
    if not matches:
        matches = [course for course in discovered if _normalize_course_key(_course_key(course)) == normalized_query]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        preferred = _preferred_course(matches)
        if preferred:
            return preferred
        choices = ", ".join(f"{course_keys[course.id]} ({course.id})" for course in matches)
        raise LMSExtractError(f"Course key '{course_query}' is ambiguous. Matching courses: {choices}.")

    if query.isdigit():
        number_matches = [
            course
            for course in discovered
            if _normalize_course_key(course_keys[course.id]).endswith(normalized_query)
            or _normalize_course_key(_course_key(course)).endswith(normalized_query)
        ]
        if len(number_matches) == 1:
            return number_matches[0]
        if len(number_matches) > 1:
            preferred = _preferred_course(number_matches)
            if preferred:
                return preferred
            choices = ", ".join(f"{course_keys[course.id]} ({course.id})" for course in number_matches)
            raise LMSExtractError(f"Course number '{course_query}' is ambiguous. Matching courses: {choices}.")

    if query.isdigit():
        course_url = client.site_url(f"course/view.php?id={query}")
        return Course(id=query, name="", url=course_url)

    available = ", ".join(course_keys[course.id] for course in discovered) or "none found"
    raise LMSExtractError(f"Course '{course_query}' was not found. Available course keys: {available}.")


def _course_key(course: Course) -> str:
    return base_course_key(course.name, course.id)


def _course_keys(courses: list[Course]) -> dict[str, str]:
    keys: dict[str, str] = {}
    for course in courses:
        keys[course.id] = display_course_key(course.name, course.id)

    return keys


def _preferred_course(courses: list[Course]) -> Course | None:
    lecture_courses = [course for course in courses if is_lecture_course(course.name)]
    if len(lecture_courses) == 1:
        return lecture_courses[0]
    return None


def _normalize_course_key(value: str) -> str:
    return "".join(char for char in collapse_whitespace(value).casefold() if char.isalnum())


def _collect_resources(client: MoodleClient, courses: list[Course], topic: str | None) -> list[Resource]:
    resources: list[Resource] = []
    for course in courses:
        course_topics = client.get_course_topics(course.id, course.name or None)
        if topic:
            course_topics = _filter_topics(course_topics, topic)
            if not course_topics:
                raise LMSExtractError(f"No topic matching '{topic}' was found in course {course.id}.")
        for course_topic in course_topics:
            resources.extend(course_topic.resources)
    return resources


def _filter_topics(topics: list[Topic], topic: str) -> list[Topic]:
    normalized = topic.casefold().strip()
    exact = [item for item in topics if item.name.casefold().strip() == normalized]
    if exact:
        return exact
    return [item for item in topics if normalized in item.name.casefold()]


def _print_courses(courses: list[Course]) -> None:
    table = Table(title="Discovered Courses")
    table.add_column("Course Key", style="cyan", no_wrap=True)
    table.add_column("Moodle ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("URL")
    course_keys = _course_keys(courses)
    for course in courses:
        table.add_row(course_keys[course.id], course.id, course.name, course.url)
    console.print(table)


def _print_topics(topics: list[Topic]) -> None:
    table = Table(title="Course Topics")
    table.add_column("Section", style="cyan", no_wrap=True)
    table.add_column("Topic")
    table.add_column("Resources", justify="right")
    for topic in topics:
        table.add_row(topic.section_id, topic.name, str(len(topic.resources)))
    console.print(table)


def _print_download_results(results: list, *, dry: bool) -> None:
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for result in results:
        resource = result.prepared.resource
        grouped[(resource.course_name, resource.course_id)].append(result)

    root = Tree("Planned downloads" if dry else "Download results")
    for (course_name, course_id), course_results in grouped.items():
        course_node = root.add(f"[bold cyan]{course_name}[/bold cyan] [dim]({course_id})[/dim]")
        by_topic: dict[str, list] = defaultdict(list)
        for result in course_results:
            by_topic[result.prepared.resource.topic].append(result)
        for topic, topic_results in by_topic.items():
            topic_node = course_node.add(topic)
            for result in topic_results:
                label = result.output_path or result.prepared.resource.title
                if result.status == "failed":
                    topic_node.add(f"[red]failed[/red] {label} - {result.message}")
                elif result.status == "skipped":
                    detail = f" - {result.message}" if result.message else ""
                    topic_node.add(f"[yellow]skipped[/yellow] {label}{detail}")
                elif result.status == "planned":
                    topic_node.add(f"[blue]planned[/blue] {label}")
                else:
                    topic_node.add(f"[green]downloaded[/green] {label}")
    console.print(root)

    failures = [result for result in results if result.status == "failed"]
    if failures:
        raise typer.Exit(code=1)


def _fail(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=1)
