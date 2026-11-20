# Base images are pinned by tag and index digest, so a scanner can read the patch; Dependabot moves both.
FROM docker.io/library/node:26.13.1-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS web

WORKDIR /src

# Manifests first, so a source-only change reuses this layer.
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund --prefer-offline

# Vite's transform cache is a build mount; the output is an ordinary layer.
COPY web/ ./
RUN --mount=type=cache,target=/src/node_modules/.vite,sharing=locked \
    npm run build

FROM docker.io/library/python:3.15-alpine@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd

LABEL org.opencontainers.image.title="emuplane" \
      org.opencontainers.image.description="Emuplane console, control API and AWS gateway" \
      org.opencontainers.image.source="https://github.com/mathewmusango/emuplane" \
      org.opencontainers.image.licenses="MIT"

# No .pyc files in the image, and logs stream out unbuffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The digest pins where the image starts, not what it ships: Alpine publishes a security fix into
# its repository before the official image is rebuilt, so a pinned base can lag by days. Taking the
# upgrade here closes that gap, and the scan runs on every build, so a base that moves ahead shows
# up as a green gate rather than a silent patch.
RUN apk upgrade --no-cache

# The runtime id is fixed, so a mount, a policy or a log line can name it.
RUN addgroup -S -g 10001 emuplane \
    && adduser -S -D -H -u 10001 -G emuplane emuplane

WORKDIR /app

# One pin, installed before the sources so editing `control/` reuses this layer.
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --no-compile -r requirements.txt

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
# pip is dead weight at runtime: the one pinned dependency is installed above and stays.
# The paths glob, because a base-image bump moves the interpreter's directory with it.
RUN rm -rf /usr/local/lib/python3.*/site-packages/pip \
    /usr/local/lib/python3.*/site-packages/pip-*.dist-info \
    /usr/local/lib/python3.*/site-packages/README.txt

USER 10001:10001
CMD ["python", "/app/app.py"]
