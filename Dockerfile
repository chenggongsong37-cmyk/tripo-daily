FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
ENV HOST=0.0.0.0
CMD ["python", "-m", "tripo_daily.web"]
