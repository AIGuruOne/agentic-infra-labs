# Stdlib only — no pip install, no wheels, no architecture-specific artefacts.
# The image builds in seconds on any host and `kind load` side-loads it, so an
# attendee on x86 Linux or WSL2 gets a native image without knowing it happened.
FROM python:3.12-slim

WORKDIR /app
COPY app.py /app/app.py
COPY model-config.json /etc/model/config.json

EXPOSE 8080
CMD ["python", "-u", "/app/app.py"]
