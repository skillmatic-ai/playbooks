FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Non-root user for security
RUN useradd -m agent
USER agent

ENTRYPOINT ["python", "-m", "src.entrypoint"]
