FROM ubuntu:24.04
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    g++ ninja-build libxml2 libnuma1 libzstd1 zlib1g ca-certificates \
    && rm -rf /var/lib/apt/lists/*
