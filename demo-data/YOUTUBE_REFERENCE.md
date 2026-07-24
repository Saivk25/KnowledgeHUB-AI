# YouTube seed reference

The seventh source type this project's ingestion pipeline supports
(alongside PDF, DOCX, PPTX, Markdown, source code, and image/OCR) is a
YouTube video transcript, via `POST /api/v1/documents/youtube` (see
`app/services/youtube.py`).

This source type is deliberately **not** auto-ingested by
`demo-data/seed.py`. `fetch_transcript()` makes a real, live network call
to YouTube's caption endpoint for one specific, real public video --
that is neither a deterministic build step nor something a seed script
should depend on succeeding (the video could be taken down, have its
captions disabled, or simply be unreachable from a given machine's
network). It also has no file representation to check into version
control the way the other six fixtures do.

## Reference video

Use any short, caption-enabled, publicly available educational video.
As of this writing, a good example is a MIT OpenCourseWare lecture clip
with auto-generated captions -- pick one from
<https://www.youtube.com/@mitocw> if the video used previously has
become unavailable. Because this reference is external and outside this
project's control, no specific URL is hardcoded here as a permanent
guarantee; treat whichever URL you use as disposable and swap it for
another captioned video if it stops working.

## Manual ingestion steps

1. Start the stack (`docker compose up`) and log in as the demo user
   (see `demo-data/seed.py`'s `--email`/`--password` defaults).
2. `POST /api/v1/documents/youtube` with `{"url": "<youtube-watch-url>"}`,
   or use the frontend's "Add from YouTube" action.
3. Poll `GET /api/v1/documents/{id}` the same way as any other upload --
   the resulting resource is an ordinary `content_source=FILE` resource
   (filename `youtube_{video_id}.txt`) once the transcript is fetched,
   indistinguishable from any other text upload from that point on.

## Fallback if the reference becomes unavailable

If the chosen video is ever removed, has captions disabled, or
`fetch_transcript()` raises `TranscriptUnavailableError` (422
`TRANSCRIPT_UNAVAILABLE`), pick a different caption-enabled public video
and repeat the same three steps above -- there is no dependency anywhere
else in this project on that transcript's specific content, only on the
mechanism being demonstrable.
