FROM --platform=linux/amd64 eclipse-temurin:21-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

ARG MB_VERSION=v0.59.6.3
RUN mkdir -p /app /plugins /metabase-data \
    && curl -fsSL https://downloads.metabase.com/${MB_VERSION}/metabase.jar -o /app/metabase.jar

WORKDIR /app
EXPOSE 3000
ENTRYPOINT ["java", "-jar", "/app/metabase.jar"]
