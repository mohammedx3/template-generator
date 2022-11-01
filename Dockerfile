FROM python:3.11-bullseye

COPY requirements.txt ./
COPY values.yaml ./
ADD template_generator.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["./template_generator.py"]