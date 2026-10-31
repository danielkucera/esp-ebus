#include "config/config_manager.hpp"

#include <esp_err.h>
#include <nvs.h>
#include <nvs_flash.h>

#include <cstdio>
#include <cstdlib>
#include <ebus/detail/json_reader.hpp>
#include <ebus/detail/json_writer.hpp>
#include <string>
#include <vector>

#include "app/app.hpp"
#include "app/app_limits.hpp"
#include "config/app_config_loader.hpp"
#include "network/http.hpp"
#include "network/http_utils.hpp"
#include "system/device_status.hpp"

extern ConfigManager config_manager;

namespace {

constexpr const char* nvs_namespace = "esp-ebus";

bool ensureNvsReady() {
  static bool nvs_ready = false;
  if (nvs_ready) return true;

  esp_err_t err = nvs_flash_init();
  if (err == ESP_ERR_NVS_NO_FREE_PAGES ||
      err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    nvs_flash_erase();
    err = nvs_flash_init();
  }
  if (err != ESP_OK) return false;

  nvs_ready = true;
  return true;
}

// Static buffer for NVS string reads - avoids heap allocation
// NVS keys are typically config values (SSID, hostnames, etc.) under 128 bytes
// But use 512 to be safe for larger values like certificates or JSON configs
static char nvs_string_buffer[512];

std::string_view readString(nvs_handle_t handle, const char* key,
                            const char* fallback = "") {
  size_t required = 0;
  esp_err_t err = nvs_get_str(handle, key, nullptr, &required);
  if (err == ESP_ERR_NVS_NOT_FOUND) {
    // Fallback is a string literal, safe to return as string_view
    return fallback;
  }
  if (err != ESP_OK || required == 0) {
    return fallback;
  }

  // Ensure buffer is large enough (required includes null terminator)
  if (required > sizeof(nvs_string_buffer)) {
    // Not enough space - truncate to max that fits
    required = sizeof(nvs_string_buffer) - 1;
  }

  err = nvs_get_str(handle, key, nvs_string_buffer, &required);
  if (err != ESP_OK) {
    return fallback;
  }

  // nvs_get_str always null-terminates, so we can use the simple constructor
  // which will stop at the null terminator. This also handles empty strings.
  return std::string_view(nvs_string_buffer);
}

bool writeString(nvs_handle_t handle, const char* key, const std::string& value,
                 std::string& error) {
  const esp_err_t err = nvs_set_str(handle, key, value.c_str());
  if (err != ESP_OK) {
    char err_buf[128];
    snprintf(err_buf, sizeof(err_buf), "Failed to write key '%s': %s", key,
             esp_err_to_name(err));
    error = err_buf;
    return false;
  }
  return true;
}

bool parseStoredBool(std::string_view value) {
  return value == "selected" || value == "true" || value == "1" ||
         value == "on";
}

bool readEntryValueAsString(nvs_handle_t handle, const nvs_entry_info_t& info,
                            std::string& out) {
  switch (info.type) {
    case NVS_TYPE_STR: {
      out = readString(handle, info.key);
      return true;
    }
    case NVS_TYPE_I8: {
      int8_t value = 0;
      if (nvs_get_i8(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(value);
      return true;
    }
    case NVS_TYPE_U8: {
      uint8_t value = 0;
      if (nvs_get_u8(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(value);
      return true;
    }
    case NVS_TYPE_I16: {
      int16_t value = 0;
      if (nvs_get_i16(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(value);
      return true;
    }
    case NVS_TYPE_U16: {
      uint16_t value = 0;
      if (nvs_get_u16(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(value);
      return true;
    }
    case NVS_TYPE_I32: {
      int32_t value = 0;
      if (nvs_get_i32(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(value);
      return true;
    }
    case NVS_TYPE_U32: {
      uint32_t value = 0;
      if (nvs_get_u32(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(value);
      return true;
    }
    case NVS_TYPE_I64: {
      int64_t value = 0;
      if (nvs_get_i64(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(static_cast<long long>(value));
      return true;
    }
    case NVS_TYPE_U64: {
      uint64_t value = 0;
      if (nvs_get_u64(handle, info.key, &value) != ESP_OK) return false;
      out = std::to_string(static_cast<unsigned long long>(value));
      return true;
    }
    default:
      return false;
  }
}

void fillJsonFromNvs(ebus::detail::JsonWriter& writer, nvs_handle_t handle) {
  nvs_iterator_t it = nullptr;
  if (nvs_entry_find("nvs", nvs_namespace, NVS_TYPE_ANY, &it) != ESP_OK) {
    return;
  }
  while (it != nullptr) {
    nvs_entry_info_t info{};
    nvs_entry_info(it, &info);

    // Never serve credentials: the config editor treats a missing password
    // as "keep the stored one", so omitting them here is lossless. See
    // AppConfig::mergeFlatJson for the matching keep-on-empty rule.
    const bool is_secret = std::strcmp(info.key, "wifiPassword") == 0 ||
                           std::strcmp(info.key, "mqttPass") == 0 ||
                           std::strcmp(info.key, "apModePassword") == 0;
    if (!is_secret) {
      std::string value;
      if (readEntryValueAsString(handle, info, value)) {
        writer.writeField(info.key, value);
      }
    }

    if (nvs_entry_next(&it) != ESP_OK) {
      break;
    }
  }
  nvs_release_iterator(it);
}

}  // namespace

std::string_view ConfigManager::readString(const char* key,
                                           const char* fallback) {
  if (!ensureNvsReady()) return fallback;

  nvs_handle_t handle = 0;
  const esp_err_t open_err = nvs_open(nvs_namespace, NVS_READONLY, &handle);
  if (open_err != ESP_OK) return fallback;

  std::string_view value = ::readString(handle, key, fallback);
  nvs_close(handle);
  return value;
}

int32_t ConfigManager::readInt(const char* key, int32_t fallback) {
  if (!ensureNvsReady()) return fallback;

  nvs_handle_t handle = 0;
  const esp_err_t open_err = nvs_open(nvs_namespace, NVS_READONLY, &handle);
  if (open_err != ESP_OK) return fallback;

  int32_t value = fallback;
  esp_err_t err = nvs_get_i32(handle, key, &value);
  if (err == ESP_OK) {
    nvs_close(handle);
    return value;
  }

  // Backward compatibility for values stored as strings.
  std::string_view str_value = ::readString(handle, key);
  nvs_close(handle);
  if (str_value.empty()) return fallback;

  char* end = nullptr;
  const long parsed = std::strtol(str_value.data(), &end, 10);
  if (end == str_value.data() || *end != '\0') return fallback;
  return static_cast<int32_t>(parsed);
}

bool ConfigManager::readBool(const char* key, bool fallback) {
  return parseStoredBool(readString(key, fallback ? "selected" : ""));
}

bool ConfigManager::writeString(const char* key, const std::string& value) {
  if (!ensureNvsReady()) return false;

  nvs_handle_t handle = 0;
  const esp_err_t open_err = nvs_open(nvs_namespace, NVS_READWRITE, &handle);
  if (open_err != ESP_OK) return false;

  std::string error;
  const bool ok = ::writeString(handle, key, value, error);
  if (!ok) {
    nvs_close(handle);
    return false;
  }

  const esp_err_t commit_err = nvs_commit(handle);
  nvs_close(handle);
  return commit_err == ESP_OK;
}

void ConfigManager::resetConfig() {
  if (!ensureNvsReady()) return;

  nvs_handle_t handle = 0;
  const esp_err_t open_err = nvs_open(nvs_namespace, NVS_READWRITE, &handle);
  if (open_err != ESP_OK) return;

  const esp_err_t erase_err = nvs_erase_all(handle);
  if (erase_err == ESP_OK) {
    nvs_commit(handle);
  }

  nvs_close(handle);
}

namespace {
esp_err_t handleConfigGet(httpd_req_t* req) {
  return config_manager.handleGet(req);
}

esp_err_t handleConfigSet(httpd_req_t* req) {
  return config_manager.handleSet(req);
}

esp_err_t handleConfigReset(httpd_req_t* req) {
  return config_manager.handleReset(req);
}

// Staged-vs-live drift: NVS (requested, incl. unapplied saves) vs the
// running snapshot (applied). Key names only — safe for HTTP.
esp_err_t handleConfigDrift(httpd_req_t* req) {
  AppConfig requested;
  AppConfigLoader loader(config_manager);
  if (!loader.load(requested)) {
    HttpUtils::sendErrorResponse(req, "500 Internal Server Error", "drift",
                                 "Config load failed");
    return ESP_OK;
  }
  std::vector<std::string> keys;
  AppConfig::collectDrift(DeviceStatus::config(), requested, keys);
  httpd_resp_set_type(req, "application/json;charset=utf-8");
  HttpUtils::applyCustomHeaders(req);
  HttpUtils::ChunkedResponse response(req);
  {
    ebus::detail::JsonWriter writer([&response](std::string_view chunk) {
      response.write(chunk);
    });
    auto root = writer.objectScope();
    writer.writeField("staged", !keys.empty());
    writer.appendKey("keys");
    {
      auto arr = writer.arrayScope();
      for (const auto& k : keys) writer.writeValue(std::string_view(k));
    }
  }
  return response.finish();
}
}  // namespace

void ConfigManager::begin() { ensureNvsReady(); }

void ConfigManager::registerHandlers() {
  // Requires a running HTTP server (see SetupHttpHandlers): called from
  // App::initHttp, not from begin().
  registerUri("/api/v1/app/config", HTTP_GET, handleConfigGet);
  registerUri("/api/v1/app/config", HTTP_POST, handleConfigSet);
  registerUri("/api/v1/app/config/reset", HTTP_POST, handleConfigReset);
  registerUri("/api/v1/app/config/drift", HTTP_GET, handleConfigDrift);
}

void ConfigManager::fetchConfig(const ebus::JsonChunkVisitor& visitor) {
  if (!ensureNvsReady()) {
    visitor("{}");
    return;
  }

  nvs_handle_t handle = 0;
  const esp_err_t open_err = nvs_open(nvs_namespace, NVS_READONLY, &handle);
  // A missing namespace is normal on first setup. Still serve defaults.
  if (open_err != ESP_OK && open_err != ESP_ERR_NVS_NOT_FOUND) {
    visitor("{}");
    return;
  }

  AppConfig defaults;
  defaults.reset();
  ebus::detail::JsonWriter writer(visitor);
  {
    auto root = writer.objectScope();
    {
      auto config = writer.objectScope("config");
      if (open_err == ESP_OK) fillJsonFromNvs(writer, handle);
    }
    {
      auto fields = writer.objectScope("fields");
      auto field = [&](const char* name, const auto& value) {
        auto item = writer.objectScope(name);
        writer.writeField("default", value);
      };
      auto numeric = [&](const char* name, unsigned value, unsigned min,
                         unsigned max) {
        auto item = writer.objectScope(name);
        writer.writeField("default", value);
        writer.writeField("min", min);
        writer.writeField("max", max);
      };
      field("wifiSsid", defaults.network.wifi_ssid.c_str());
      field("wifiBssid", defaults.network.wifi_bssid.c_str());
      field("staticIPEnabled", defaults.network.static_ip_enabled);
      field("ipAddress", defaults.network.ip_address.c_str());
      field("gateway", defaults.network.gateway.c_str());
      field("netmask", defaults.network.netmask.c_str());
      field("dns1", defaults.network.dns1.c_str());
      field("dns2", defaults.network.dns2.c_str());
      field("thingName", defaults.mqtt_ha.thing_name.c_str());
      field("sntpEnabled", defaults.sntp.enabled);
      field("sntpServer", defaults.sntp.server.c_str());
      field("sntpTimezone", defaults.sntp.timezone.c_str());
      numeric("pwmValue", defaults.pwm.value, app::limits::Pwm::min,
              app::limits::Pwm::max);
      field("ebusAddress", defaults.bus.address.c_str());
      numeric("busWindow", defaults.bus.window_us,
              app::limits::Bus::window_min_us, app::limits::Bus::window_max_us);
      field("systemInquiry", defaults.bus.system_inquiry);
      field("systemResponse", defaults.bus.system_response);
      field("scanOnStartup", defaults.bus.scan_on_startup);
      field("mqttEnabled", defaults.mqtt.enabled);
      field("mqttServer", defaults.mqtt.server.c_str());
      field("mqttUser", defaults.mqtt.user.c_str());
      field("rootTopic", defaults.mqtt.root_topic.c_str());
      field("haEnabled", defaults.mqtt_ha.enabled);
      field("httpHeaders", defaults.http.headers.c_str());
      // Passwords are never returned, including reset defaults.
    }
  }
  writer.flush();
  if (open_err == ESP_OK) nvs_close(handle);
}

bool ConfigManager::writeConfigJson(std::string_view body, std::string& error) {
  if (!ensureNvsReady()) {
    error = "Failed to initialize NVS";
    return false;
  }

  ebus::detail::JsonReader reader(body);
  if (reader.next() != ebus::detail::JsonReader::Token::object_start) {
    error = "JSON root must be an object";
    return false;
  }

  nvs_handle_t handle = 0;
  const esp_err_t open_err = nvs_open(nvs_namespace, NVS_READWRITE, &handle);
  if (open_err != ESP_OK) {
    error = std::string("Failed to open NVS: ") + esp_err_to_name(open_err);
    return false;
  }

  bool dirty = false;
  bool ok = true;

  while (ok) {
    auto token = reader.next();
    if (token == ebus::detail::JsonReader::Token::object_end ||
        token == ebus::detail::JsonReader::Token::end)
      break;
    if (token == ebus::detail::JsonReader::Token::key) {
      std::string key(reader.value());
      if (reader.next() == ebus::detail::JsonReader::Token::string) {
        std::string value(reader.value());
        // Keep-on-empty for credentials (mirrors AppConfig::mergeFlatJson):
        // an empty password means "keep the stored one", never "clear it".
        if (value.empty() && (key == "wifiPassword" || key == "mqttPass" ||
                              key == "apModePassword")) {
          continue;
        }
        if (!::writeString(handle, key.c_str(), value, error)) {
          ok = false;
        }
        dirty = true;
      } else {
        error = "Unsupported value type for key '" + key + "'";
        ok = false;
      }
    }
  }

  if (dirty && ok) {
    nvs_commit(handle);
  }
  nvs_close(handle);
  return ok;
}

esp_err_t ConfigManager::handleGet(httpd_req_t* req) {
  HttpUtils::ChunkedResponse response(req);
  httpd_resp_set_type(req, "application/json;charset=utf-8");
  HttpUtils::applyCustomHeaders(req);
  fetchConfig([&response](std::string_view chunk) {
    response.write(chunk);
  });
  return response.finish();
}

esp_err_t ConfigManager::handleSet(httpd_req_t* req) {
  HttpUtils::StreamingReader sr(req);
  if (!sr.isValid() || !sr.feedAll()) {
    HttpUtils::sendErrorResponse(req, "400 Bad Request", "config_set",
                                 "Request body too large or invalid");
    return ESP_OK;
  }
  sr.endOfInput();
  std::string error;
  bool success = false;
  if (App::instance() != nullptr) {
    // Canonical path: validate + persist via the AppConfig snapshot.
    success = App::instance()->applyFlatConfigJson(sr.jsonReader().remaining(),
                                                   error);
  } else {
    success = writeConfigJson(sr.jsonReader().remaining(), error);
  }
  if (success) {
    HttpUtils::sendSuccessResponse(req, "config_set", "successful",
                                   "Config saved to NVS");
  } else {
    HttpUtils::sendErrorResponse(req, "400 Bad Request", "config_set", error);
  }
  return ESP_OK;
}

esp_err_t ConfigManager::handleReset(httpd_req_t* req) {
  resetConfig();
  HttpUtils::sendSuccessResponse(req, "config_reset", "successful",
                                 "Config reset");
  return ESP_OK;
}
