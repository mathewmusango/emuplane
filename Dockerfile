# MiniStack control plane: the React console, the control API and the AWS
# gateway in one image.
#
#   podman build -t localhost/ministack-control:dev .
#
# Base images are pinned by **index digest** (multi-arch) so a rebuild resolves
# to the same bytes; `renovate.json` is what should move them.
#
# The first stage builds `web/dist`, so the runtime image is self-contained:
# nothing is bind-mounted from the host and nothing has to be built there.
# The emulator stays a separate upstream image (see docker-compose.yml).

FROM docker.io/library/node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS web

WORKDIR /src

# Manifests first: a source-only change reuses this layer, and npm's own cache
# is a build mount, so it speeds rebuilds without landing in an image layer.
# `--prefer-offline` keeps a warm cache from waiting on the registry.
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund --prefer-offline

# Vite keeps a transform cache under `node_modules/.vite`. Mounting it as a
# build cache is what makes the second and later builds of changed source fast:
# unchanged modules are not re-transformed. The output (`dist`) is a normal
# layer, so nothing from the cache ships in the image.
COPY web/ ./
RUN --mount=type=cache,target=/src/node_modules/.vite,sharing=locked \
    npm run build


FROM docker.io/library/python:3.13-alpine@sha256:7984cf56ceaddebe4fefeb75d64000b9f45d8b77b11a09b24524da6cdc3af0c8

LABEL org.opencontainers.image.title="ministack-control" \
      org.opencontainers.image.description="MiniStack console, control API and AWS gateway" \
      org.opencontainers.image.source="https://github.com/mathewmusango/ministack-control" \
      org.opencontainers.image.licenses="MIT"

# No .pyc files in the image, and logs stream out unbuffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Only what the control reads at runtime. The console was built in the stage
# above, so `web/public` is already part of `dist`. `dist` comes first so that
# editing `control/` only rewrites the small layer after it.
COPY --from=web /src/dist /app/static
COPY control/app.py control/buckets.py control/console.py control/dynamo.py control/signed.py \
     control/s3extra.py control/store.py control/api_token.py control/password.py \
     control/backends.py control/mail.py /app/
# The first-setup init job and the stack it applies (`docker-compose.yml` runs
# it as the `bootstrap` service, before the control starts).
COPY bootstrap /app/bootstrap

# The control API, and the AWS gateway that fronts the emulator.
EXPOSE 8080 8081

# The healthcheck lives in docker-compose.yml: podman's default OCI image format
# ignores `HEALTHCHECK`, and a warning on every build is worse than the
# declaration being in one place.
#
# Runs as root on purpose: the control state is a host bind mount, and rootless
# podman maps it to the container's root, not to an unprivileged user.
CMD ["python", "/app/app.py"]
