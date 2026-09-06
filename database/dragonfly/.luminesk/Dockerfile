FROM golang:1.26-bookworm

WORKDIR /src
RUN git init \
    && git remote add origin https://github.com/df-mc/dragonfly.git \
    && git fetch --depth 1 origin a36ed0edb548298ab482939e1c653e39f9683719 \
    && git checkout --detach FETCH_HEAD
RUN mkdir /out \
    && CGO_ENABLED=0 go build \
        -buildvcs=false \
        -mod=readonly \
        -trimpath \
        -ldflags="-s -w -buildid=" \
        -o /out/dragonfly .
