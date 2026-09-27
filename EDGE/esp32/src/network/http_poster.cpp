#include "http_poster.h"

#ifdef ARDUINO

HttpPoster::HttpPoster() {}

IngestResult HttpPoster::sendObservation(
    const char* endpoint_url,
    const char* json_payload,
    uint8_t max_retries,
    uint32_t backoff_base_ms
) {
    if (!endpoint_url || !json_payload) {
        return INGEST_VALIDATION_ERROR;
    }

    for (uint8_t attempt = 0; attempt <= max_retries; ++attempt) {
        if (attempt > 0) {
            uint32_t backoff = backoff_base_ms * (1 << (attempt - 1));
            Serial.printf("[HttpPoster] Retry attempt %u/%u after %u ms...\n",
                          attempt, max_retries, backoff);
            delay(backoff);
        }

        if (!_http.begin(endpoint_url)) {
            Serial.println(F("[HttpPoster] HTTP begin failed."));
            continue;
        }

        _http.addHeader("Content-Type", "application/json");
        _http.setTimeout(10000);

        int httpCode = _http.POST((uint8_t*)json_payload, strlen(json_payload));

        if (httpCode > 0) {
            String response = _http.getString();
            _http.end();

            if (httpCode == 200) {
                Serial.printf("[HttpPoster] Success (200 OK): %s\n", response.c_str());
                return INGEST_SUCCESS;
            } else if (httpCode == 409) {
                Serial.printf("[HttpPoster] Duplicate event accepted (409 Conflict): %s\n", response.c_str());
                return INGEST_DUPLICATE_ACCEPTED;
            } else if (httpCode == 404) {
                Serial.printf("[HttpPoster] Station not registered (404 Not Found): %s\n", response.c_str());
                return INGEST_UNKNOWN_STATION;
            } else if (httpCode == 422 || httpCode == 400) {
                Serial.printf("[HttpPoster] Ingestion schema error (%d): %s\n", httpCode, response.c_str());
                return INGEST_VALIDATION_ERROR;
            } else if (httpCode >= 500) {
                Serial.printf("[HttpPoster] Backend server error (%d): %s\n", httpCode, response.c_str());
                // Will retry if attempt < max_retries
            } else {
                Serial.printf("[HttpPoster] Unexpected HTTP status %d: %s\n", httpCode, response.c_str());
            }
        } else {
            Serial.printf("[HttpPoster] Connection failed: %s\n", _http.errorToString(httpCode).c_str());
            _http.end();
        }
    }

    return INGEST_NETWORK_TIMEOUT;
}

#endif
