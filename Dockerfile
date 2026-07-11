FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# T-Invest API's TLS certificate (invest-public-api.tbank.ru / sandbox-invest-public-api.tbank.ru)
# is issued by Russia's Ministry of Digital Development root CA, which is not in any
# standard OS trust store - without this, gRPC calls to the API fail with "self-signed
# certificate in certificate chain" even though the certificate itself is legitimate.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget \
    && wget -q https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt \
         -O /usr/local/share/ca-certificates/russian_trusted_root_ca.crt \
    && wget -q https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt \
         -O /usr/local/share/ca-certificates/russian_trusted_sub_ca.crt \
    && update-ca-certificates \
    && apt-get purge -y --auto-remove wget \
    && rm -rf /var/lib/apt/lists/*

# grpc-python ships its own compiled-in root certificate bundle and does NOT use the OS
# trust store above by default - this makes it fall back to the (now-updated) system
# bundle, which is what actually lets the T-Invest SDK trust the certificate.
ENV GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt

COPY pyproject.toml README.md ./
COPY app ./app

# t-tech-investments (the T-Invest SDK) is published on T-Bank's own index, not PyPI -
# see README "Setup" for why.
RUN pip install . --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple

RUN mkdir -p /app/data/cache

CMD ["python", "-m", "app.main"]
