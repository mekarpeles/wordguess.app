FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . /app

ENV FLASK_APP=app.py
EXPOSE 5050

CMD ["python", "app.py"]
