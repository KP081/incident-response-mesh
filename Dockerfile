# syntax=docker/dockerfile:1
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Dependencies pehle install karo (cached layer -- code badalne pe ye layer
# dobara nahi banega, sirf dependencies badalne pe)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Ab poora project code copy karo
COPY . /app

ENV HITL_CAPTURE_ONLY=true
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD ["sh", "-c", "exec streamlit run streamlit_app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]