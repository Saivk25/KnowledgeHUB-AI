"""
YouTube transcript fetch (Milestone 5).

Decision (see docs/adr/0012-multi-format-extraction.md): a YouTube video has
no uploaded file, but Milestone 4's Resource model was deliberately built
with FILE as the only implemented content_source. Rather than building a
second, fileless ingestion path this milestone (that is Vision v2's Capture
work, explicitly out of scope until its own milestone), a YouTube resource is
represented as an ordinary content_source=FILE resource: the transcript text
is fetched here, saved to local storage as a plain .txt file through the
existing `services/storage.py`, and from that point on it is indistinguishable
from any other uploaded text file -- extracted by TextExtractor, chunked,
embedded, and indexed through the exact same pipeline, with the exact same
status machine and retry/delete routes.

Security note (DRR Section 6, SSRF): this does not fetch an arbitrary
user-supplied URL. `extract_video_id` only accepts youtube.com/youtu.be URL
shapes and extracts an 11-character video ID via regex; the only outbound
request this module makes is the `youtube_transcript_api` library's own call
to YouTube's caption endpoint for that specific, validated video ID -- there
is no code path here that opens a socket to an arbitrary host.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class InvalidYoutubeUrlError(Exception):
    pass


class TranscriptUnavailableError(Exception):
    pass


def extract_video_id(url: str) -> str:
    """Accepts youtube.com/watch?v=ID, youtu.be/ID, youtube.com/embed/ID,
    and youtube.com/shorts/ID. Raises InvalidYoutubeUrlError for anything
    else -- including non-YouTube hosts, which is the actual SSRF guard."""

    try:
        parsed = urlparse(url.strip())
    except ValueError as exc:
        raise InvalidYoutubeUrlError("Could not parse this URL.") from exc

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    if parsed.scheme not in ("http", "https"):
        raise InvalidYoutubeUrlError("Only http(s) YouTube URLs are supported.")

    video_id: str | None = None
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.removeprefix("/embed/").split("/")[0]
        elif parsed.path.startswith("/shorts/"):
            video_id = parsed.path.removeprefix("/shorts/").split("/")[0]

    if not video_id or not _VIDEO_ID_RE.match(video_id):
        raise InvalidYoutubeUrlError("This does not look like a valid YouTube video URL.")

    return video_id


def fetch_transcript(video_id: str) -> str:
    """Fetches the video's transcript and joins every segment's text with a
    newline. This is the one seam tests replace (monkeypatch) rather than
    hitting the real network -- see tests/test_youtube_ingestion.py -- the
    same "mock only the external boundary" discipline already used for the
    OpenAI-backed providers in services/embeddings.py."""

    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
        YouTubeTranscriptApi,
    )

    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id)
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as exc:
        raise TranscriptUnavailableError("No transcript is available for this video.") from exc

    text = "\n".join(segment["text"] for segment in segments if segment.get("text"))
    if not text.strip():
        raise TranscriptUnavailableError("No transcript is available for this video.")
    return text
