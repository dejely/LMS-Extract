from lms_extrafiliator.parser import parse_course_title, parse_courses, parse_login_token, parse_topics


def test_parse_login_token() -> None:
    html = '<input type="hidden" name="logintoken" value="abc123">'
    assert parse_login_token(html) == "abc123"


def test_parse_courses_deduplicates_by_course_id() -> None:
    html = """
    <a href="/course/view.php?id=42">Biology 101</a>
    <a href="https://lms.test/course/view.php?id=42">Duplicate</a>
    <a href="/course/view.php?id=7" title="Chemistry">Ignored text</a>
    """
    courses = parse_courses(html, "https://lms.test")
    assert [course.id for course in courses] == ["7", "42"]
    assert courses[0].name == "Chemistry"
    assert courses[1].name == "Biology 101"


def test_parse_topics_and_resources() -> None:
    html = """
    <ul>
      <li class="section" data-sectionid="1">
        <h3 class="sectionname">Week 1</h3>
        <a href="/mod/resource/view.php?id=100"><span class="instancename">Lecture Notes</span></a>
        <a href="/pluginfile.php/1/mod_resource/content/0/slides.pdf">Slides</a>
      </li>
      <li class="section" data-sectionid="2">
        <h3 class="sectionname">Week 2</h3>
        <a href="/forum/view.php?id=200">Forum</a>
      </li>
    </ul>
    """
    topics = parse_topics(
        html,
        "https://lms.test",
        "42",
        "https://lms.test/course/view.php?id=42",
        "Biology 101",
    )
    assert [topic.name for topic in topics] == ["Week 1", "Week 2"]
    assert topics[0].course_name == "Biology 101"
    assert len(topics[0].resources) == 2
    assert topics[0].resources[0].course_name == "Biology 101"
    assert topics[0].resources[0].title == "Lecture Notes"
    assert topics[1].resources == []


def test_parse_course_title_from_moodle_heading() -> None:
    html = """
    <div class="page-header-headings">
      <h1>Math 101 - Calculus</h1>
    </div>
    """
    assert parse_course_title(html, "42") == "Math 101 - Calculus"
