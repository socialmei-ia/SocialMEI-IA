FROM python:3.12-slim

ARG SOCIALMEI_RELEASE_SHA=unknown
ENV SOCIALMEI_RELEASE_SHA=$SOCIALMEI_RELEASE_SHA
LABEL org.opencontainers.image.revision=$SOCIALMEI_RELEASE_SHA

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
