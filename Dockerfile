# StaffPicked: Emby and Jellyfin collections and playlists from MDBList, Trakt and your own lists.
# Everything you edit lives in the /config volume; the image holds only the app.
# Pinned to one Alpine release so a rebuild doesn't change the base under us; Dependabot bumps it.
FROM python:3.13-alpine3.24

# the release build passes the tag's version (it must match scripts/__init__.py) and commit
ARG VERSION=dev
ARG REVISION=
LABEL org.opencontainers.image.title="StaffPicked" \
      org.opencontainers.image.description="Emby and Jellyfin collections and playlists from MDBList, Trakt and your own lists" \
      org.opencontainers.image.licenses="GPL-3.0-only" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

# tzdata lets TZ set the time zone that SYNC_TIME is read in;
# tini reaps the sync processes the web UI starts and forwards stop signals
RUN apk add --no-cache tzdata tini

WORKDIR /app
COPY scripts/ /app/scripts/
COPY web/ /app/web/
COPY docker/ /app/docker/
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
RUN chmod 755 /app/docker/staffpicked && ln -s /app/docker/staffpicked /usr/local/bin/staffpicked
# examples the web UI copies into an empty /config on first start
COPY config/ /app/defaults/

ENV PYTHONUNBUFFERED=1 \
    STAFFPICKED_CONFIG=/config \
    STAFFPICKED_DEFAULTS=/app/defaults \
    TZ=UTC \
    PORT=9343
VOLUME /config
EXPOSE 9343
# healthy while the web UI answers and its daily scheduler is running (Dockge, Portainer and
# `docker ps` show it); busybox wget comes with Alpine
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${PORT}/api/health" || exit 1
# The web UI on port 9343. It also runs the daily sync (SYNC_TIME, SYNC_ON_START).
# The entrypoint makes /config writable for its owner (or PUID:PGID) and runs everything as that user.
# Command line: docker exec -it staffpicked staffpicked check
ENTRYPOINT ["/sbin/tini", "--", "python", "/app/docker/entrypoint.py"]
CMD ["python", "/app/web/server.py"]
