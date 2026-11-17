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

FROM docker.io/library/python:3.13-alpine@sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e

LABEL org.opencontainers.image.title="emuplane" \
      org.opencontainers.image.description="Emuplane console, control API and AWS gateway" \
      org.opencontainers.image.source="https://github.com/mathewmusango/emuplane" \
      org.opencontainers.image.licenses="MIT"

# No .pyc files in the image, and logs stream out unbuffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The runtime id is fixed, so a mount, a policy or a log line can name it.
RUN addgroup -S -g 10001 emuplane \
    && adduser -S -D -H -u 10001 -G emuplane emuplane

WORKDIR /app

# The built console first, so editing `control/` only rewrites the layer after it.
COPY --chown=10001:10001 --from=web /src/dist /app/static
COPY --chown=10001:10001 control/app.py control/accesspoints.py control/buckets.py \
     control/console.py control/dynamo.py control/signed.py \
     control/s3extra.py control/store.py control/api_token.py control/password.py \
     control/backends.py control/mail.py /app/
# The first-setup job, so `docker compose run bootstrap` needs no mount or checkout.
COPY --chown=10001:10001 bootstrap /app/bootstrap

# The control API, and the AWS gateway that fronts the emulator.
EXPOSE 4570 4571

# Declared in docker-compose.yml, because podman's OCI format ignores HEALTHCHECK.
# The control and the bootstrap are standard-library only: pip's vendored tree is dead weight here.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
    /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
    /usr/local/lib/python3.13/site-packages/README.txt

USER 10001:10001
CMD ["python", "/app/app.py"]
