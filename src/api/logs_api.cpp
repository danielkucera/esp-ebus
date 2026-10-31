#include "api/logs_api.hpp"

#if defined(EBUS_INTERNAL)

#include <esp_timer.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#include "network/http.hpp"
#include "network/http_utils.hpp"
#include "system/device_status.hpp"
#include "system/system_monitor.hpp"

namespace {

// cppcheck-suppress syntaxError
extern const char logs_html_start[] asm("_binary_logs_html_start");

}  // namespace

LogsApi* LogsApi::instance_ = nullptr;

LogsApi::LogsApi(Logger& logger) : logger_(logger) { instance_ = this; }

bool LogsApi::registerHandlers(httpd_handle_t server) {
  if (server == nullptr) return false;

  registerUri("/logs", HTTP_GET, handleLogsPage);
  registerUri("/api/v1/app/logs", HTTP_GET, handleLogs);
  registerUri("/api/v1/app/logs/time-relation", HTTP_GET,
              handleLogsTimeRelation);
#if EBUS_BUS_TAP
  registerUri("/api/v1/app/tap", HTTP_GET, handleTap);
#endif

  return true;
}

esp_err_t LogsApi::handleLogsPage(httpd_req_t* req) {
  HttpUtils::sendResponse(req, "200 OK", "text/html", logs_html_start);
  return ESP_OK;
}

esp_err_t LogsApi::handleLogs(httpd_req_t* req) {
  HttpUtils::ChunkedResponse response(req);
  uint64_t since_millis = 0;
  const size_t query_len = httpd_req_get_url_query_len(req);
  if (query_len > 0) {
    char query_buf[256];
    if (query_len + 1 > sizeof(query_buf)) {
      httpd_resp_send_err(req, HTTPD_414_URI_TOO_LONG, nullptr);
      return ESP_OK;
    }
    if (httpd_req_get_url_query_str(req, query_buf, sizeof(query_buf)) ==
        ESP_OK) {
      char since_buffer[32] = {0};
      if (httpd_query_key_value(query_buf, "since", since_buffer,
                                sizeof(since_buffer)) == ESP_OK) {
        since_millis = std::strtoull(since_buffer, nullptr, 10);
      }
    }
  }
  // A since value beyond the current uptime comes from before a restart.
  constexpr uint64_t restart_margin_ms = 1000;
  const uint64_t uptime_ms = esp_timer_get_time() / 1000ULL;
  if (since_millis > uptime_ms + restart_margin_ms) since_millis = 0;
  httpd_resp_set_type(req, "application/json;charset=utf-8");
  HttpUtils::applyCustomHeaders(req);
  instance_->logger_.fetchLogs(
      [&response](std::string_view chunk) {
        response.write(chunk);
      },
      since_millis);
  return response.finish();
}

esp_err_t LogsApi::handleLogsTimeRelation(httpd_req_t* req) {
  HttpUtils::ChunkedResponse response(req);
  httpd_resp_set_type(req, "application/json;charset=utf-8");
  HttpUtils::applyCustomHeaders(req);
  instance_->logger_.fetchTimeRelation([&response](std::string_view chunk) {
    response.write(chunk);
  });
  return response.finish();
}

esp_err_t LogsApi::handleTap(httpd_req_t* req) {
  HttpUtils::ChunkedResponse response(req);
  uint64_t since_millis = 0;
  const size_t query_len = httpd_req_get_url_query_len(req);
  if (query_len > 0) {
    char query_buf[256];
    if (query_len + 1 > sizeof(query_buf)) {
      httpd_resp_send_err(req, HTTPD_414_URI_TOO_LONG, nullptr);
      return ESP_OK;
    }
    if (httpd_req_get_url_query_str(req, query_buf, sizeof(query_buf)) ==
        ESP_OK) {
      char since_buffer[32] = {0};
      if (httpd_query_key_value(query_buf, "since", since_buffer,
                                sizeof(since_buffer)) == ESP_OK) {
        since_millis = std::strtoull(since_buffer, nullptr, 10);
      }
    }
  }
  httpd_resp_set_type(req, "application/json;charset=utf-8");
  HttpUtils::applyCustomHeaders(req);
  DeviceStatus::monitor().fetchTap(
      [&response](std::string_view chunk) {
        response.write(chunk);
      },
      since_millis);
  return response.finish();
}

#endif
