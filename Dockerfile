FROM golang:1.21-alpine AS builder
RUN apk add --no-cache git make
WORKDIR /app
RUN go install github.com/posthog/duckgres/cmd/duckgres@latest

FROM debian:book-slim
RUN apt-get update && apt-get install -y ca-certificates libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /go/bin/duckgres /usr/local/bin/duckgres
RUN mkdir -p /data /config

EXPOSE 5432 9090
ENTRYPOINT ["duckgres"]
CMD ["--config", "/config/duckgres.yaml"]
