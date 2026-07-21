# Milestone 1 + Milestone 2 + Milestone 3 image. Only requirements.txt is
# installed -- no dev tooling (pytest/ruff/black). PyMuPDF's wheel bundles
# MuPDF statically; empirically verified (see Milestone 3 verification) to
# need no extra OS packages for text extraction on python:3.11-slim, so
# none are added here. If a later milestone renders PDF pages as images
# (thumbnails, OCR), revisit this -- that path can need libgl1/libglib2.0-0.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
