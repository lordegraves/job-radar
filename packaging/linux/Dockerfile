# Build the Linux artifact in Linux; PyInstaller output cannot be cross-built on Windows.
FROM python:3.13-slim-bookworm AS builder

WORKDIR /build
RUN apt-get update \
    && apt-get install --yes --no-install-recommends binutils \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY job_radar ./job_radar
COPY packaging/linux ./packaging/linux

RUN python -m pip install --no-cache-dir ".[dev]"
RUN python -m PyInstaller \
    --clean \
    --noconfirm \
    --workpath /build/work \
    --distpath /build/dist \
    /build/packaging/linux/junior.spec
RUN cp /build/packaging/linux/launch-junior.sh /build/dist/Junior/ \
    && cp /build/packaging/linux/install.sh /build/dist/Junior/ \
    && cp /build/packaging/linux/uninstall.sh /build/dist/Junior/ \
    && chmod +x /build/dist/Junior/junior /build/dist/Junior/*.sh \
    && tar -C /build/dist -czf /build/Junior-linux-x86_64.tar.gz Junior

FROM scratch AS artifact
COPY --from=builder /build/Junior-linux-x86_64.tar.gz /
