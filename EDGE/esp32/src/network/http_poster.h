#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef ARDUINO
#include <Arduino.h>
#include <HTTPClient.h>

enum IngestResult {
    INGEST_SUCCESS,            // HTTP 200 OK
    INGEST_DUPLICATE_ACCEPTED, // HTTP 409 Conflict (already ingested)
    INGEST_VALIDATION_ERROR,   // HTTP 422 Unprocessable / 400 Bad Request
    INGEST_UNKNOWN_STATION,    // HTTP 404 Not Found
    INGEST_SERVER_ERROR,       // HTTP 5xx Internal Error
    INGEST_NETWORK_TIMEOUT     // Failed to connect / timeout
};

class HttpPoster {
public:
    HttpPoster();
    
    /**
     * Submits a serialized JSON ObservationPacket to the backend ingestion endpoint.
     * Implements bounded retry logic reusing identical packet data on retry.
     */
    IngestResult sendObservation(
        const char* endpoint_url,
        const char* json_payload,
        uint8_t max_retries = 3,
        uint32_t backoff_base_ms = 500
    );

private:
    HTTPClient _http;
};
#endif
