FROM debian:latest

RUN apt-get update && \
    apt-get install -y libreoffice python3 python3-pip imagemagick && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY convert.py /app/convert.py
COPY entrypoint.sh /app/entrypoint.sh
COPY process.sh /app/process.sh
COPY policy.xml /etc/ImageMagick-6/policy.xml

RUN chmod +x /app/entrypoint.sh /app/process.sh

ENTRYPOINT ["/app/process.sh"]