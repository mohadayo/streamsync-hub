FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod .
COPY *.go .
RUN go build -o processor .

FROM alpine:3.20
WORKDIR /app
COPY --from=builder /app/processor .
EXPOSE 8081
CMD ["./processor"]
