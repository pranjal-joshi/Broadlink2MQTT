ARG BUILD_FROM
# The tag is supplied per architecture by build.yaml, so it cannot be pinned here.
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# The .pth makes /app/src importable from site-packages, so finding our own
# code never depends on PYTHONPATH surviving. Written via site.getsitepackages()
# rather than a hardcoded path so it follows the base image's Python version.
# Combined into one RUN because hadolint runs at failure-threshold=info (DL3059).
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt \
    && python3 -c "import pathlib, site; pathlib.Path(site.getsitepackages()[0], 'broadlink2mqtt.pth').write_text('/app/src\n')"

COPY src/ /app/src/

# s6-overlay runs CMD with a cleaned environment: Dockerfile ENV *and* runtime
# `-e` / compose `environment:` values are both stripped, which left the bridge
# unable to see any of its configuration. with-contenv re-imports the container
# environment from /run/s6/container_environment before exec'ing.
CMD ["/usr/bin/with-contenv", "python3", "-m", "broadlink2mqtt"]
