FROM debian:bookworm-slim

# 精简镜像：bash 工具链 + python3 + ripgrep（nodejs 依赖链过大，M1 沙箱不装）
# apt 源偶发 502：内置 5 次重试
RUN set -eux; \
    for i in 1 2 3 4 5; do \
        apt-get update \
        && apt-get install -y --no-install-recommends --fix-missing \
            bash coreutils findutils grep \
            ripgrep fd-find jq \
            python3 python3-minimal \
            ca-certificates \
        && break || { echo "[apt retry $i]"; sleep 10; }; \
    done; \
    rm -rf /var/lib/apt/lists/*

COPY jail.py /usr/local/bin/jail
RUN chmod 755 /usr/local/bin/jail \
    && useradd -m -u 1000 -s /bin/bash agent \
    && mkdir -p /workspace \
    && chown -R agent:agent /workspace

USER 1000:1000
WORKDIR /workspace

# 容器长驻由 sleep infinity 维持；exec 经由 docker exec 注入
CMD ["sleep", "infinity"]
