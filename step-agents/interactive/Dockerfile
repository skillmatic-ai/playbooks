FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY step_agent/ ./step_agent/
COPY entrypoint.py .
COPY skills/ ./skills/

RUN useradd -m agent
USER agent

ENTRYPOINT ["python", "entrypoint.py"]
