#pragma once

#include <esp_http_server.h>

#include <ebus/detail/json_reader.hpp>
#include <algorithm>
#include <cstring>
#include <string>
#include <string_view>

namespace HttpUtils {

constexpr size_t max_request_body_size = 8192;
constexpr size_t streaming_buffer_size = 4096;

// Coalesce small JSON fragments and stop socket I/O after the first failure.
// Call finish() after all writers/scopes have emitted their closing bytes.
class ChunkedResponse {
 public:
  explicit ChunkedResponse(httpd_req_t* req) : req_(req) {}
  ChunkedResponse(const ChunkedResponse&) = delete;
  ChunkedResponse& operator=(const ChunkedResponse&) = delete;

  void write(std::string_view chunk) {
    while (!finished_ && result_ == ESP_OK && !chunk.empty()) {
      const size_t count = std::min(chunk.size(), sizeof(buffer_) - size_);
      std::memcpy(buffer_ + size_, chunk.data(), count);
      size_ += count;
      chunk.remove_prefix(count);
      if (size_ == sizeof(buffer_)) flush();
    }
  }

  esp_err_t finish() {
    if (!finished_) {
      flush();
      if (result_ == ESP_OK) result_ = httpd_resp_send_chunk(req_, nullptr, 0);
      finished_ = true;
    }
    return result_;
  }

 private:
  void flush() {
    if (result_ == ESP_OK && size_ > 0) {
      result_ = httpd_resp_send_chunk(req_, buffer_, size_);
      size_ = 0;
    }
  }

  httpd_req_t* req_;
  char buffer_[1024];
  size_t size_ = 0;
  esp_err_t result_ = ESP_OK;
  bool finished_ = false;
};

class StreamingReader {
 public:
  explicit StreamingReader(httpd_req_t* req);
  ~StreamingReader();
  StreamingReader(const StreamingReader&) = delete;
  StreamingReader& operator=(const StreamingReader&) = delete;

  bool feedAll();
  void endOfInput() const;
  ebus::detail::JsonReader& jsonReader();
  bool isValid() const { return valid_; }

 private:
  httpd_req_t* req_;
  std::string fallback_body_;
  ebus::detail::JsonReader fallback_reader_;
  bool valid_ = false;
  bool use_streaming_ = false;
};

bool registerRoute(httpd_handle_t server, const httpd_uri_t& route);
bool registerRoute(httpd_handle_t server, const char* uri,
                   httpd_method_t method, esp_err_t (*handler)(httpd_req_t*));

void sendResponse(httpd_req_t* req, const char* status, const char* type,
                  const char* body);
void sendResponse(httpd_req_t* req, const char* status, const char* type,
                  const std::string& body);

std::string readBody(httpd_req_t* req);

// Parse and store custom headers (format: "Name: Value" lines,
// newline-separated). Must be called once at startup; stored headers are
// applied to every response.
void setCustomHeaders(const std::string& raw);

// Sends a standardized JSON error response.
void sendErrorResponse(httpd_req_t* req, const char* status,
                       std::string_view id, std::string_view error_message);

// Sends a standardized JSON success response.
void sendSuccessResponse(httpd_req_t* req, std::string_view id,
                         std::string_view status = "successful",
                         std::string_view message = "");

// Applies the currently stored custom headers to the given HTTP response.
// Useful for handlers that use chunked/streaming responses.
void applyCustomHeaders(httpd_req_t* req);

// Helper to prepare a JsonReader for iterating over an array of commands/keys.
// Handles both bare arrays and objects with a specific array key (e.g.,
// {"commands": [...]}). On success, the reader is positioned at the start of
// the array. On failure, returns false and populates error_out.
bool prepareJsonReaderForArray(ebus::detail::JsonReader& reader,
                               std::string_view expected_array_key,
                               std::string& error_out);

}  // namespace HttpUtils
