FROM python:3.11-bullseye

COPY requirements.txt ./
ADD ./template ./template
ADD ./test ./test
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR ./template
ENTRYPOINT ["./template_generator.py"]