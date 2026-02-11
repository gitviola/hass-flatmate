ARG BUILD_FROM
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apk add --no-cache \
    python3 \
    py3-pip

WORKDIR /opt/hass_flatmate

COPY service_src /opt/hass_flatmate
COPY rootfs/ /

RUN pip3 install --no-cache-dir --break-system-packages .

CMD ["/run.sh"]
