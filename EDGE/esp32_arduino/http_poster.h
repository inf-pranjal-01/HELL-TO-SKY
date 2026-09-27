#pragma once

#ifdef ARDUINO
#include <HTTPClient.h>
#endif

#include <stdint.h>

typedef enum {
    INGEST_SUCCESS,
    INGEST_DUPLICATE_ACCEPTED,
    INGEST_NETWORK_TIMEOUT,
    INGEST_UNKNOWN_STATION,
    INGEST_VALIDATION_ERROR
} IngestResult;

#ifdef ARDUINO

class HttpPoster {
public:
    HttpPoster();
    IngestResult sendObservation(
        const char* endpoint_url,
        const char* json_payload,
        uint8_t max_retries,
        uint32_t backoff_base_ms
    );

private:
    HTTPClient _http;
};

#endif
