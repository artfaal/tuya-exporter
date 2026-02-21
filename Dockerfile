FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tuya_exporter.py .
COPY wizard.py .

RUN mkdir -p logs

CMD ["python", "tuya_exporter.py"]
