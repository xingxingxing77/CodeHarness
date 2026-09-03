FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash coreutils findutils grep \
        ripgrep fd-find jq \
        python3 python3-minimal \
        nodejs npm \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY jail.py /usr/local/bin/jail
RUN chmod 755 /usr/local/bin/jail \
    && useradd -m -u 1000 -s /bin/bash agent \
    && mkdir -p /workspace \
    && chown -R agent:agent /workspace

USER 1000:1000
WORKDIR /workspace

# 容器长驻由 sleep infinity 维持；exec 经由 docker exec 注入
CMD ["sleep", "infinity"]
