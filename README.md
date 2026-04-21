# LMS Extrafiliator

`lms-extract` is a CLI tool for downloading files from Moodle-style Learning Management Systems using an authorized account.

It creates a local folder tree like:

```text
downloads/
  COURSE_NAME_BEFORE_FIRST_HYPHEN/
    TOPIC_NAME/
      file.pdf
      slides.pptx
```

## Setup

Install dependencies:

```bash
uv sync --extra dev
```

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
LMS_BASE_URL=https://your-moodle-site.edu
LMS_USERNAME=your_username
LMS_PASSWORD=your_password
DOWNLOAD_DIR=downloads
LMS_AUTH_MODE=http
LMS_LOGIN_PATH=auto
```

Never commit `.env`. It is ignored by git.

## Usage

List enrolled courses:

```bash
uv run lms-extract courses
```

List topics in a course:

```bash
uv run lms-extract topics --course "CMSC 126"
```

Preview downloads:

```bash
uv run lms-extract dry-run --course "CMSC 126"
uv run lms-extract dry-run --all
uv run lms-extract dry-run --all "25-26"
```

Download files:

```bash
uv run lms-extract download --course "CMSC 126"
uv run lms-extract download --course "CMSC 126" --topic "Week 1"
uv run lms-extract download --all
uv run lms-extract download --all "25-26"
```

When using `--all`, you can add an academic year filter such as `25-26`; it matches course names containing forms like `25-26`, `2025-26`, or `2025-2026`.

Use `uv run lms-extract courses` to see each course key. The key is normally the Moodle course name up to, but excluding, the first `-`; for example, `CMSC 126 - Web Programming - Section 1` is selected with `--course "CMSC 126"`. If lecture and lab courses share the same base key, the lecture keeps the base key and the lab adds `Lab`, such as `CMSC 127` and `CMSC 127 Lab`. Compact keys like `cmsc126` also work. A bare course number like `126` works when it uniquely identifies one discovered course. Moodle numeric IDs still work as a fallback.

Dry runs and downloads check both the manifest and existing files under `DOWNLOAD_DIR`. If a matching file is already present, including in an older numeric course folder, the item is reported as skipped instead of creating a duplicate. A real `download` run migrates matching files from old numeric course folders into the current course-name folder and updates the manifest.

Course folders use the same course key shown by `lms-extract courses`. For example, `CMSC 101 - Introduction to Computing` becomes `downloads/CMSC 101/`, while `CMSC 101 - Laboratory - Section 1` becomes `downloads/CMSC 101 Lab/`.

## Browser Login Fallback

If your Moodle site uses SSO, MFA, or JavaScript-heavy login, capture browser cookies:

```bash
uv run lms-extract auth browser
```

Then set:

```env
LMS_AUTH_MODE=browser
```

The browser cookie file is stored under `.lms-extract/`, which is ignored by git.

## UPV LMS IV

For `https://lms.upvisayas.net/login.php`, set:

```env
LMS_BASE_URL=https://lms.upvisayas.net
LMS_LOGIN_PATH=login.php
LMS_AUTH_MODE=http
```

If normal login fails because of the site policy modal or account flow, use the browser fallback and then set `LMS_AUTH_MODE=browser`.

## Notes

- This tool only follows pages and downloads available to the authenticated account.
- It does not bypass Moodle permissions, enrollment checks, CAPTCHA, MFA, or access controls.
- Completed downloads are tracked in `.lms-extract/manifest.json` so reruns can skip existing files.
