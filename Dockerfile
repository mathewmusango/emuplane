# Emuplane: the console, the control API and the AWS gateway in one image.
#   podman build -t localhost/emuplane:dev .

# Base images are pinned by index digest; `renovate.json` moves them.
FROM docker.io/library/node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS web

WORKDIR /src

# Manifests first, so a source-only change reuses this layer.
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund --prefer-offline

# Vite's transform cache is a build mount; the output is an ordinary layer.
COPY web/ ./
RUN --mount=type=cache,target=/src/node_modules/.vite,sharing=locked \
    npm run build


FROM docker.io/library/python:3.13-alpine@sha256:7984cf56ceaddebe4fefeb75d64000b9f45d8b77b11a09b24524da6cdc3af0c8

LABEL org.opencontainers.image.title="emuplane" \
      org.opencontainers.image.description="Emuplane console, control API and AWS gateway" \
      org.opencontainers.image.source="https://github.com/mathewmusango/emuplane" \
      org.opencontainers.image.licenses="MIT"

# No .pyc files in the image, and logs stream out unbuffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# The built console first, so editing `control/` only rewrites the layer after it.
COPY --from=web /src/dist /app/static
COPY control/app.py control/accesspoints.py control/buckets.py control/console.py \
     control/dynamo.py control/signed.py \
     control/s3extra.py control/store.py control/api_token.py control/password.py \
     control/backends.py control/mail.py /app/
# The first-setup job and the stack it applies.
COPY bootstrap /app/bootstrap

# The control API, and the AWS gateway that fronts the emulator.
EXPOSE 8080 8081

# Declared in docker-compose.yml, because podman's OCI format ignores HEALTHCHECK.
# Root on purpose: the control state is a host bind mount.
CMD ["python", "/app/app.py"]
