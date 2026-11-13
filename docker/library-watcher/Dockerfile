# library_watcher sidecar: stdlib-only poll loop over the source trees (spec 0004, ADR 0005).
# The repo is bind-mounted read-only at /tools (PYTHONPATH), so no code is baked in.
# git is required: `import` commits playlist history via history.py's `git -C <library>` calls.
FROM python:3.13.18-alpine
RUN apk add --no-cache git
