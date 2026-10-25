#include <catch2/catch_test_macros.hpp>
#include <string>

#include "config/app_config_loader.hpp"
#include "app/app_limits.hpp"
#include <ebus/detail/json_reader.hpp>
#include "config/config_manager.hpp"

// The ConfigManager instance backing these tests. NVS itself is the
// in-memory host mock (test_host/mocks/config/nvs_mock.cpp), so each case
// starts from resetConfig() for isolation.
ConfigManager config_manager;

TEST_CASE("ConfigManager string roundtrip", "[config_nvs]") {
  config_manager.resetConfig();

  REQUIRE(ConfigManager::writeString("wifiSsid", "my-ssid") == true);
  REQUIRE(std::string(ConfigManager::readString("wifiSsid")) == "my-ssid");

  // Overwrite works.
  REQUIRE(ConfigManager::writeString("wifiSsid", "other") == true);
  REQUIRE(std::string(ConfigManager::readString("wifiSsid")) == "other");

  // Missing keys yield the fallback.
  REQUIRE(std::string(ConfigManager::readString("nope", "fb")) == "fb");
  REQUIRE(std::string(ConfigManager::readString("nope")) == "");
}

TEST_CASE("ConfigManager int parsing matches firmware semantics",
          "[config_nvs]") {
  config_manager.resetConfig();

  REQUIRE(ConfigManager::writeString("busWindow", "4300") == true);
  REQUIRE(ConfigManager::readInt("busWindow", 4400) == 4300);

  // Non-numeric content falls back (strtol failure path).
  REQUIRE(ConfigManager::writeString("busWindow", "abc") == true);
  REQUIRE(ConfigManager::readInt("busWindow", 4400) == 4400);

  // Missing keys fall back.
  REQUIRE(ConfigManager::readInt("busWindow", 4400) == 4400);
}

TEST_CASE("ConfigManager bool parsing matches firmware semantics",
          "[config_nvs]") {
  config_manager.resetConfig();

  for (auto truthy : {"true", "1", "selected", "on"}) {
    REQUIRE(ConfigManager::writeString("sntpEnabled", truthy) == true);
    REQUIRE(ConfigManager::readBool("sntpEnabled") == true);
  }
  for (auto falsy : {"false", "0", "", "nope"}) {
    REQUIRE(ConfigManager::writeString("sntpEnabled", falsy) == true);
    REQUIRE(ConfigManager::readBool("sntpEnabled") == false);
  }
  // Missing keys yield the fallback.
  config_manager.resetConfig();
  REQUIRE(ConfigManager::readBool("sntpEnabled", true) == true);
  REQUIRE(ConfigManager::readBool("sntpEnabled") == false);
}

TEST_CASE("ConfigManager resetConfig clears stored keys", "[config_nvs]") {
  REQUIRE(ConfigManager::writeString("wifiSsid", "my-ssid") == true);
  config_manager.resetConfig();
  REQUIRE(std::string(ConfigManager::readString("wifiSsid", "fb")) == "fb");
}

TEST_CASE("ConfigManager fetchConfig dumps stored keys", "[config_nvs]") {
  config_manager.resetConfig();
  REQUIRE(ConfigManager::writeString("wifiSsid", "my-ssid") == true);

  std::string out;
  ConfigManager::fetchConfig([&out](std::string_view chunk) {
    out.append(chunk.data(), chunk.size());
  });
  REQUIRE(out.find("my-ssid") != std::string::npos);
}

TEST_CASE("AppConfigLoader save/load roundtrip", "[config_nvs]") {
  config_manager.resetConfig();

  AppConfig written;
  written.reset();
  written.network.wifi_ssid.assign("my-ssid");
  written.pwm.value = 200;
  written.bus.window_us = 4300;
  written.bus.address.assign("01");
  written.sntp.enabled = true;
  written.mqtt.server.assign("mqtt.local");

  AppConfigLoader loader(config_manager);
  REQUIRE(loader.save(written) == true);

  AppConfig loaded;
  REQUIRE(loader.load(loaded) == true);
  REQUIRE(std::string(loaded.network.wifi_ssid.c_str()) == "my-ssid");
  REQUIRE(loaded.pwm.value == 200);
  REQUIRE(loaded.bus.window_us == 4300);
  REQUIRE(std::string(loaded.bus.address.c_str()) == "01");
  REQUIRE(loaded.sntp.enabled == true);
  REQUIRE(std::string(loaded.mqtt.server.c_str()) == "mqtt.local");
  // Untouched keys carry reset defaults.
  REQUIRE(loaded.bus.offset_us == 50);
}

TEST_CASE("AppConfigLoader load overlays stored keys on defaults",
          "[config_nvs]") {
  config_manager.resetConfig();
  REQUIRE(ConfigManager::writeString("pwmValue", "210") == true);

  AppConfig loaded;
  AppConfigLoader loader(config_manager);
  REQUIRE(loader.load(loaded) == true);
  REQUIRE(loaded.pwm.value == 210);
  REQUIRE(loaded.bus.window_us == 4400);
}

TEST_CASE("Config API supplies firmware defaults and limits without secrets", "[config_nvs]") {
  config_manager.resetConfig();
  REQUIRE(ConfigManager::writeString("wifiPassword", "stored-wifi-secret"));
  REQUIRE(ConfigManager::writeString("apModePassword", "stored-ap-secret"));
  REQUIRE(ConfigManager::writeString("mqttPass", "stored-mqtt-secret"));
  REQUIRE(ConfigManager::writeString("busWindow", "4300"));
  std::string out;
  ConfigManager::fetchConfig([&](std::string_view chunk) { out += chunk; });
  AppConfig defaults;
  defaults.reset();
  auto number = [&](const char* name, const char* property) {
    ebus::detail::JsonReader reader(out);
    reader.next();
    REQUIRE(reader.findKey("fields"));
    reader.next();
    REQUIRE(reader.findKey(name));
    reader.next();
    REQUIRE(reader.findKey(property));
    reader.next();
    return reader.asNum<unsigned>();
  };
  REQUIRE(number("pwmValue", "default") == defaults.pwm.value);
  REQUIRE(number("pwmValue", "min") == app::limits::Pwm::min);
  REQUIRE(number("pwmValue", "max") == app::limits::Pwm::max);
  REQUIRE(number("busWindow", "default") == defaults.bus.window_us);
  REQUIRE(number("busWindow", "min") == app::limits::Bus::window_min_us);
  REQUIRE(number("busWindow", "max") == app::limits::Bus::window_max_us);
  REQUIRE(number("busOffset", "default") == defaults.bus.offset_us);
  REQUIRE(number("busOffset", "min") == app::limits::Bus::offset_min_us);
  REQUIRE(number("busOffset", "max") == app::limits::Bus::offset_max_us);
  REQUIRE(out.find("4300") != std::string::npos);
  for (auto secret : {"wifiPassword", "apModePassword", "mqttPass",
                      "stored-wifi-secret", "stored-ap-secret", "stored-mqtt-secret",
                      defaults.network.wifi_password.c_str(),
                      defaults.network.ap_password.c_str()}) {
    REQUIRE(out.find(secret) == std::string::npos);
  }
}

TEST_CASE("Empty stored configuration still supplies page defaults", "[config_nvs]") {
  config_manager.resetConfig();
  std::string out;
  ConfigManager::fetchConfig([&](std::string_view chunk) { out += chunk; });
  REQUIRE(out.find("\"config\":{}") != std::string::npos);
  REQUIRE(out.find("\"fields\":{") != std::string::npos);
  REQUIRE(out.find("\"ebusAddress\":{\"default\":\"ff\"}") != std::string::npos);
}
