#pragma once

#include <cstdint>
#include <string_view>

// How command values are published under "<root>/values/".
enum class MqttPayloadMode : uint8_t {
  // values/<command> -> {"<field>":v,...} (one JSON object per command)
  json_multivalue,
  // values/<field> -> {"value":v} (one topic per field of multi-field commands)
  json_singlevalue,
  // values/<field> -> v (one topic per field, raw scalar)
  plain
};

inline constexpr std::string_view mqttPayloadModeName(MqttPayloadMode mode) {
  switch (mode) {
    case MqttPayloadMode::json_singlevalue:
      return "json_single";
    case MqttPayloadMode::plain:
      return "plain";
    case MqttPayloadMode::json_multivalue:
    default:
      return "json_multi";
  }
}

// Unknown or empty names fall back to json_multivalue.
inline constexpr MqttPayloadMode parseMqttPayloadMode(std::string_view name) {
  if (name == "json_single") return MqttPayloadMode::json_singlevalue;
  if (name == "plain") return MqttPayloadMode::plain;
  return MqttPayloadMode::json_multivalue;
}
