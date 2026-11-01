FROM python:3.12.16-slim-trixie@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

RUN apt-get update && apt-get -y upgrade && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tuya_exporter.py .
COPY wizard.py .

RUN mkdir -p logs

CMD ["python", "tuya_exporter.py"]
