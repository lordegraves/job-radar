# Run the same Junior web application with one persistent user-data mount.
FROM python:3.13-slim-bookworm

ARG JUNIOR_UID=10001
ARG JUNIOR_GID=10001

RUN groupadd --gid "${JUNIOR_GID}" junior \
    && useradd --uid "${JUNIOR_UID}" --gid "${JUNIOR_GID}" \
        --home-dir /var/lib/junior --create-home junior

WORKDIR /app
COPY pyproject.toml README.md ./
COPY job_radar ./job_radar
COPY packaging/container/entrypoint.sh /usr/local/bin/junior-container-entrypoint

RUN python -m pip install --no-cache-dir . gunicorn==23.0.0 \
    && chmod 0555 /usr/local/bin/junior-container-entrypoint \
    && chown -R junior:junior /var/lib/junior

ENV JOB_RADAR_DATA_DIR=/var/lib/junior
ENV JUNIOR_HOST=0.0.0.0
ENV JUNIOR_PORT=8000

VOLUME ["/var/lib/junior"]
EXPOSE 8000
USER junior:junior

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('JUNIOR_PORT','8000') + '/health', timeout=3)"

ENTRYPOINT ["junior-container-entrypoint"]
