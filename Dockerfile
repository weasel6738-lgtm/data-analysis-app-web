FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt ./requirements.txt
COPY backend/requirements-ai.txt ./backend/requirements-ai.txt
RUN pip install --no-cache-dir -r requirements.txt -r backend/requirements-ai.txt
COPY backend ./backend
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/_stcore/health')"
CMD ["sh", "-c", "streamlit run backend/streamlit_app.py --server.address 0.0.0.0 --server.port ${PORT} --server.headless true"]
