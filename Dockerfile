FROM golang:1.26-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY idl/ ./idl/
COPY kitex_gen/ ./kitex_gen/
COPY cmd/ ./cmd/
COPY internal/ ./internal/
ARG TARGET=metadata
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/oncall-lab "./cmd/$TARGET"

FROM alpine:3.22
RUN addgroup -S app && adduser -S -G app app && mkdir -p /var/log/oncall && chown app:app /var/log/oncall
USER app
COPY --from=build /out/oncall-lab /usr/local/bin/oncall-lab
ENTRYPOINT ["/usr/local/bin/oncall-lab"]
