FROM python:3
RUN pip3 install --no-cache-dir aiohttp lxml requests
WORKDIR /app
COPY oreilly_downloader.py oreilly_login.py sso login ./
RUN chmod 0755 sso login && mv sso login /usr/bin/
RUN useradd -m appuser && chown -R appuser /app
USER appuser
