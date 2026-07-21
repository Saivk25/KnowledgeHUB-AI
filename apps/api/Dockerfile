# Milestone 1 (Project Foundation) image. Only requirements.txt is
# installed -- no dev tooling (pytest/ruff/black/httpx), and no OS packages
# for not-yet-installed future dependencies. PyMuPDF's rendering libraries
# (libglib2.0-0, libgl1) are intentionally not installed here; they belong
# in the Milestone 3 update to this Dockerfile, alongside PyMuPDF itself.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
