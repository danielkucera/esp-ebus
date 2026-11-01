// SPDX-License-Identifier: GPL-3.0-or-later
#define CATCH_CONFIG_MAIN
#include <catch2/catch_test_macros.hpp>
#include <ebus/data_types.hpp>
#include <ebus/detail/json_reader.hpp>
#include <ebus/detail/json_writer.hpp>
#include <ebus/utils.hpp>

#include "app/command.hpp"
#include "app/command_manager.hpp"

using namespace ebus::detail;

TEST_CASE("Command fromJson roundtrip preserves fields", "[Command]") {
  std::string json =
      R"({"key":"01","name":"Outside_Temperature","read_cmd":"fe070009",)"
      R"("write_cmd":"","interval":0,"master":true,)"
      R"("fields":[{"name":"value","profile":"data2b_celsius",)"
      R"("position":1,"ha_profile":"sensor_temperature"}]})";

  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);

  REQUIRE(cmd.getKey() == "01");
  REQUIRE(cmd.getName() == "Outside_Temperature");
  REQUIRE(cmd.getActive() == false);
  REQUIRE(cmd.getFieldCount() == 1);
  REQUIRE(cmd.getFieldPosition(0) == 1);
  REQUIRE(cmd.getMaster() == true);
  REQUIRE(cmd.getFieldDatatype(0) == ebus::DataType::data2b);
  REQUIRE(cmd.getFieldDivider(0) == 1);
  REQUIRE(cmd.getFieldDigits(0) == 1);
  REQUIRE(std::string(cmd.getFieldUnit(0)) == "\u00b0C");
  REQUIRE(cmd.hasFieldHA(0) == true);
  REQUIRE(std::string(cmd.getFieldHAProfileName(0)) == "sensor_temperature");
}

TEST_CASE("Command fromTabular roundtrip preserves fields", "[Command]") {
  std::string json = R"(["01","Outside_Temperature","fe070009","",0,true,)"
                     R"([{"name":"value","profile":"data2b_celsius",)"
                     R"("position":1,"ha_profile":"sensor_temperature"}])";

  JsonReader reader(json);
  Command cmd = Command::fromTabular(reader, true);

  REQUIRE(cmd.getKey() == "01");
  REQUIRE(cmd.getName() == "Outside_Temperature");
  REQUIRE(cmd.getFieldCount() == 1);
  REQUIRE(cmd.getFieldDatatype(0) == ebus::DataType::data2b);
  REQUIRE(std::string(cmd.getFieldHAProfileName(0)) == "sensor_temperature");
}

TEST_CASE("Command evaluate accepts valid command", "[Command]") {
  std::string json =
      R"({"key":"01","name":"Outside_Temperature","read_cmd":"fe070009",)"
      R"("interval":0,"master":true,)"
      R"("fields":[{"name":"value","profile":"data2b_celsius",)"
      R"("position":1,"ha_profile":"sensor_temperature"}]})";

  JsonReader reader(json);
  std::string_view error = Command::evaluate(reader);
  REQUIRE(error.empty());
}

TEST_CASE("Command evaluate rejects missing key", "[Command]") {
  std::string json = R"({"name":"Outside_Temperature","read_cmd":"fe070009",)"
                     R"("interval":0,"master":true,)"
                     R"("fields":[{"name":"value","profile":"data2b_celsius",)"
                     R"("position":1,"ha_profile":"sensor_temperature"}]})";

  JsonReader reader(json);
  std::string_view error = Command::evaluate(reader);
  REQUIRE_FALSE(error.empty());
  REQUIRE(error.find("key") != std::string_view::npos);
}

TEST_CASE("Command evaluate rejects unknown profile", "[Command]") {
  std::string json =
      R"({"key":"01","name":"Outside_Temperature","read_cmd":"fe070009",)"
      R"("interval":0,)"
      R"("fields":[{"name":"value","profile":"invalid_profile",)"
      R"("position":1,"ha_profile":"sensor_temperature"}]})";

  JsonReader reader(json);
  std::string_view error = Command::evaluate(reader);
  REQUIRE_FALSE(error.empty());
}

TEST_CASE("Command evaluate rejects missing fields", "[Command]") {
  std::string json =
      R"({"key":"01","name":"Outside_Temperature","read_cmd":"fe070009",)"
      R"("interval":0})";

  JsonReader reader(json);
  std::string_view error = Command::evaluate(reader);
  REQUIRE_FALSE(error.empty());
  REQUIRE(error.find("fields") != std::string_view::npos);
}

TEST_CASE("Command toJson serializes fields", "[Command]") {
  std::string json =
      R"({"key":"01","name":"Test","read_cmd":"fe070009","write_cmd":"",)"
      R"("interval":60,"master":true,)"
      R"("fields":[{"name":"value","profile":"data2b_celsius",)"
      R"("position":1,"ha_profile":"sensor_temperature"}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);

  std::string out;
  ebus::detail::JsonWriter writer([&out](std::string_view s) { out += s; });
  {
    auto scope = writer.objectScope();
    writer.writeField("key", cmd.getKey());
    writer.writeField("name", cmd.getName());
    writer.writeHexField("zz", cmd.getZz());
    writer.writeHexField("id", cmd.getId());
    if (cmd.hasNnOverride()) {
      writer.writeHexField("nn", cmd.getNn());
    }
    if (cmd.hasWriteCmd()) {
      writer.writeHexField("wid", cmd.getWid());
    }
    writer.writeField("interval", cmd.getInterval());

    {
      auto arr = writer.arrayScope("fields");
      for (size_t i = 0; i < cmd.getFieldCount(); i++) {
        auto field_obj = writer.objectScope();
        writer.writeField("name", cmd.getFieldName(i));
        writer.writeField("profile", cmd.getFieldProfile(i)
                                         ? cmd.getFieldProfile(i)->name
                                         : "");
        writer.writeField("position",
                          static_cast<uint32_t>(cmd.getFieldPosition(i)));
        writer.writeField("master", cmd.getMaster());
        writer.writeField("ha_profile", cmd.getFieldHAProfileName(i));
      }
    }
  }

  REQUIRE(out.find("\"key\":\"01\"") != std::string::npos);
  REQUIRE(out.find("\"name\":\"Test\"") != std::string::npos);
  REQUIRE(out.find("\"zz\":\"fe\"") != std::string::npos);
  REQUIRE(out.find("\"id\":\"0700\"") != std::string::npos);
  REQUIRE(out.find("\"nn\":\"09\"") != std::string::npos);
  REQUIRE(out.find("\"wid\"") == std::string::npos);
  REQUIRE(out.find("\"fields\"") != std::string::npos);
  REQUIRE(out.find("\"profile\":\"data2b_celsius\"") != std::string::npos);
  REQUIRE(out.find("\"position\":1") != std::string::npos);
  REQUIRE(out.find("\"master\":true") != std::string::npos);
  REQUIRE(out.find("\"ha_profile\":\"sensor_temperature\"") !=
          std::string::npos);
}

TEST_CASE("Command matches checks read_cmd at offset 1", "[Command]") {
  std::string json = R"({"key":"01","name":"Test","read_cmd":"fe070009",)"
                     R"("interval":0,"master":true,)"
                     R"("fields":[{"name":"value","profile":"uint8",)"
                     R"("position":1,"ha_profile":"sensor_temperature"}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);

  uint8_t bytes[] = {0x10, 0xfe, 0x07, 0x00, 0x09};
  ebus::ByteView master(bytes, 5);

  REQUIRE(cmd.matches(master) == true);
}

TEST_CASE("Command writeValuePayload formats single and multi fields flat",
          "[Command]") {
  SECTION("Single field") {
    std::string json = R"({"key":"09","name":"Buffer/Middle_Temperature",)"
                       R"("read_cmd":"08b50903290100","master":false,)"
                       R"("fields":[{"name":"middle_temperature",)"
                       R"("profile":"data2c_celsius","position":1,)"
                       R"("ha_profile":"sensor_temperature"}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);

    ebus::Sequence data;
    data.push_back(0x50);
    data.push_back(0x01);
    cmd.setData(ebus::ByteView(data));

    std::string out;
    ebus::detail::JsonWriter writer([&out](std::string_view s) { out += s; });
    {
      auto scope = writer.objectScope();
      cmd.writeValuePayload(writer);
    }

    REQUIRE(out.find("\"middle_temperature\":") != std::string::npos);
  }

  SECTION("Multi field") {
    std::string json = R"({"key":"09","name":"Buffer/Middle_Temperature",)"
                       R"("read_cmd":"08b50903290100","master":false,)"
                       R"("fields":[{"name":"middle_temperature",)"
                       R"("profile":"data2c_celsius","position":1,)"
                       R"("ha_profile":"sensor_temperature"},)"
                       R"({"name":"state","profile":"uint8","position":3,)"
                       R"("ha_profile":"sensor_enum_state"}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);

    ebus::Sequence data;
    data.push_back(0x50);
    data.push_back(0x01);
    data.push_back(0x55);  // 85
    cmd.setData(ebus::ByteView(data));

    std::string out;
    ebus::detail::JsonWriter writer([&out](std::string_view s) { out += s; });
    {
      auto scope = writer.objectScope();
      cmd.writeValuePayload(writer);
    }

    REQUIRE(out.find("\"middle_temperature\":") != std::string::npos);
    REQUIRE(out.find("\"state\":85") != std::string::npos);
  }
}

TEST_CASE("Command getVectorFromString demands exact bytes", "[Command]") {
  std::string json =
      R"({"key":"t1","name":"HexTest","read_cmd":"080704","write_cmd":"",)"
      R"("interval":0,"master":false,)"
      R"("fields":[{"name":"h","profile":"hex2",)"
      R"("position":1,"ha_profile":""}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);
  REQUIRE(cmd.getFieldCount() == 1);

  // Exact: 4 hex chars -> 2 bytes.
  ebus::Sequence ok = cmd.getVectorFromString("abcd", 0);
  REQUIRE(ok.size() == 2);
  REQUIRE(ok[0] == 0xab);
  REQUIRE(ok[1] == 0xcd);

  // Short, odd-length, and non-hex are rejected, not padded or zero-filled.
  REQUIRE(cmd.getVectorFromString("ab", 0).empty());
  REQUIRE(cmd.getVectorFromString("abc", 0).empty());
  REQUIRE(cmd.getVectorFromString("zz", 0).empty());
  REQUIRE(cmd.getVectorFromString("0xab", 0).empty());
}

TEST_CASE("Command getVectorFromJson rejects garbage numerics", "[Command]") {
  std::string json =
      R"({"key":"01","name":"Outside_Temperature","read_cmd":"fe070009",)"
      R"("write_cmd":"","interval":0,"master":true,)"
      R"("fields":[{"name":"value","profile":"data2b_celsius",)"
      R"("position":1,"ha_profile":"sensor_temperature"}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);
  REQUIRE(cmd.getFieldCount() == 1);

  // Garbage must not become 0 (lenient toNum wrote it silently before).
  REQUIRE(cmd.getVectorFromJson(R"({"value":"abc"})").empty());
  REQUIRE(cmd.getVectorFromJson(R"({"value":"21.5abc"})").empty());
  // Genuine values still encode.
  REQUIRE(!cmd.getVectorFromJson(R"({"value":21.5})").empty());
}

TEST_CASE("Command raw flag parses and defaults false", "[Command]") {
  std::string json =
      R"({"key":"01","name":"T","read_cmd":"fe070009",)"
      R"("write_cmd":"","interval":0,"master":true,)"
      R"("fields":[{"name":"a","profile":"data2b_celsius","position":1,)"
      R"("raw":true},{"name":"b","profile":"data2b_celsius","position":2}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);
  REQUIRE(cmd.getFieldCount() == 2);
  REQUIRE(cmd.isFieldRaw(0) == true);
  REQUIRE(cmd.isFieldRaw(1) == false);
  REQUIRE(cmd.isFieldRaw(99) == false);
}

TEST_CASE("Command evaluate accepts raw boolean, rejects raw string",
          "[Command]") {
  std::string ok =
      R"({"key":"01","name":"T","read_cmd":"fe070009","interval":0,)"
      R"("fields":[{"name":"a","profile":"data2b_celsius","position":1,)"
      R"("raw":true}]})";
  JsonReader r1(ok);
  REQUIRE(Command::evaluate(r1).empty());

  std::string bad =
      R"({"key":"01","name":"T","read_cmd":"fe070009","interval":0,)"
      R"("fields":[{"name":"a","profile":"data2b_celsius","position":1,)"
      R"("raw":"yes"}]})";
  JsonReader r2(bad);
  REQUIRE_FALSE(Command::evaluate(r2).empty());
}

TEST_CASE("Weishaupt room writes reproduce captured 5023 telegrams",
          "[Command]") {
  struct Example {
    const char* destination;
    const char* parameter;
    double value;
    const char* expected;
  };
  const Example examples[] = {{"70", "0500", 21, "70502309600500d2005d010000"},
                              {"70", "0800", 16, "70502309e00800a0005d010000"},
                              {"f0", "0500", 17, "f0502309d00500aa005d010000"},
                              {"f0", "0800", 13, "f050230994080082005d010000"},
                              {"17", "0500", 25, "17502309c40500fa005d010000"},
                              {"17", "0800", 19, "17502309cc0800be005d010000"}};
  for (const auto& ex : examples) {
    std::string json =
        std::string(
            R"({"key":"room_test","name":"Room","read_cmd":"75502203700500","write_cmd":")") +
        ex.destination + "50230900" + ex.parameter +
        R"(","write_type":"weishaupt","interval":60,"master":false,"fields":[{"name":"value","profile":"int16_celsius_div10","position":1,"min":5,"max":30}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);
    auto value = cmd.getVectorFromValue(std::to_string(ex.value));
    REQUIRE(value.size() == 2);
    auto frame = cmd.buildWriteSequence(command_manager, value);
    std::string hex;
    const char* digits = "0123456789abcdef";
    for (auto byte : frame) {
      hex += digits[byte >> 4];
      hex += digits[byte & 15];
    }
    REQUIRE(hex == ex.expected);
    REQUIRE(cmd.getVectorFromValue("31").empty());
    REQUIRE(cmd.getVectorFromValue("4").empty());
  }
}

TEST_CASE("Standard writes preserve bytes even for a 5023 prefix",
          "[Command]") {
  const char* prefixes[] = {"50b509040e3300", "70502309ab0500"};
  for (auto prefix : prefixes) {
    std::string json =
        std::string(
            R"({"key":"legacy","name":"Legacy","read_cmd":"085003019e","write_cmd":")") +
        prefix +
        R"(","interval":60,"master":false,"fields":[{"name":"value","profile":"uint16","position":1}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);
    REQUIRE(cmd.getWriteType() == command_types::WriteType::simple);
    const uint8_t value[] = {0xaa, 0x00};
    auto frame =
        cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 2));
    uint8_t prefix_buf[8];
    size_t prefix_len = ebus::toBytes(prefix, prefix_buf, sizeof(prefix_buf));
    auto expected = ebus::makeSequence(ebus::ByteView(prefix_buf, prefix_len));
    expected.append(ebus::makeSequence(ebus::ByteView(value, 2)));
    REQUIRE(frame == expected);
  }
}

TEST_CASE("Malformed opted-in writes are rejected", "[Command]") {
  const std::string json = R"({
  "key": "badwrite",
  "name": "Bad",
  "read_cmd": "085003019e",
  "write_cmd": "70502308ab0500",
  "write_type": "weishaupt",
  "fields": [
    {
      "name": "value",
      "profile": "uint16",
      "position": 1
    }
  ]
})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);
  const uint8_t value[] = {0xaa, 0x00};
  REQUIRE(cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 2))
              .empty());
  REQUIRE(cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 1))
              .empty());

  // With the correct NN prefix only the value length remains to check.
  std::string fixed_json = json;
  const size_t nn_pos = fixed_json.find("70502308");
  REQUIRE(nn_pos != std::string::npos);
  fixed_json.replace(nn_pos, 8, "70502309");
  JsonReader fixed_reader(fixed_json);
  Command fixed_cmd = Command::fromJson(fixed_reader);
  REQUIRE(
      fixed_cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 2))
          .size() == 13);
  REQUIRE(
      fixed_cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 1))
          .empty());
}

TEST_CASE("Write types reject unknown names and non-strings", "[Command]") {
  const char* settings[] = {
      R"("write_type":"other")", R"("write_type":true)",
      R"("write_type":false)",   R"("write_type":null)",
      R"("write_type":1)",       R"("write_type":"default")"};
  for (auto setting : settings) {
    const std::string json =
        std::string(
            R"({"key":"type","name":"Type","read_cmd":"085003019e","write_cmd":"70502309000500",)") +
        setting +
        R"(,"fields":[{"name":"value","profile":"uint16","position":1}]})";
    JsonReader reader(json);
    REQUIRE_FALSE(Command::evaluate(reader).empty());
    JsonReader direct_reader(json);
    Command cmd = Command::fromJson(direct_reader);
    const uint8_t value[] = {0xd2, 0};
    REQUIRE(cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 2))
                .empty());
  }
}

TEST_CASE("Explicit simple writes preserve the existing bytes", "[Command]") {
  const std::string json = R"({
  "key": "simple_type",
  "name": "Simple",
  "read_cmd": "085003019e",
  "write_cmd": "70502309ab0500",
  "write_type": "simple",
  "fields": [
    {
      "name": "value",
      "profile": "uint16",
      "position": 1
    }
  ]
})";
  JsonReader validation(json);
  REQUIRE(Command::evaluate(validation).empty());
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);
  REQUIRE(cmd.getWriteType() == command_types::WriteType::simple);
  const uint8_t value[] = {0xaa, 0};
  const uint8_t prefix_bytes[] = {0x70, 0x50, 0x23, 0x09, 0xab, 0x05, 0x00};
  auto expected =
      ebus::makeSequence(ebus::ByteView(prefix_bytes, sizeof(prefix_bytes)));
  expected.append(ebus::makeSequence(ebus::ByteView(value, 2)));
  REQUIRE(cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 2)) ==
          expected);
}

TEST_CASE("Tabular write types reject boolean and unknown values",
          "[Command]") {
  const char* types[] = {"true", "false", "\"other\""};
  for (auto type : types) {
    std::string row =
        std::string(
            R"(["tab_type","Type","75502203700500","70502309000500",60,false,[{"name":"value","profile":"uint16","position":1}],)") +
        type + "]";
    JsonReader reader(row);
    Command cmd = Command::fromTabular(reader, true);
    REQUIRE(cmd.getWriteType() == command_types::WriteType::invalid);
    const uint8_t value[] = {0xd2, 0};
    REQUIRE(cmd.buildWriteSequence(command_manager, ebus::ByteView(value, 2))
                .empty());
  }
}

TEST_CASE("Command compact schema derives read NN", "[Command]") {
  std::string json = R"({"key":"01","name":"T","zz":"fe","id":"b51601",)"
                     R"("interval":0,"master":true,)"
                     R"("fields":[{"name":"v","profile":"uint8","position":1,)"
                     R"("ha_profile":""}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);

  REQUIRE(cmd.hasNnOverride() == false);
  REQUIRE(cmd.hasWriteCmd() == false);

  uint8_t buf[10];
  size_t len = cmd.buildReadCmd(buf, sizeof(buf));
  REQUIRE(len == 5);
  REQUIRE(buf[0] == 0xfe);
  REQUIRE(buf[1] == 0xb5);
  REQUIRE(buf[2] == 0x16);
  REQUIRE(buf[3] == 0x01);  // derived NN = len(id)-2
  REQUIRE(buf[4] == 0x01);
}

TEST_CASE("Command explicit nn overrides derived NN", "[Command]") {
  std::string json =
      R"({"key":"01","name":"T","zz":"fe","id":"b51601","nn":"03",)"
      R"("interval":0,"master":true,)"
      R"("fields":[{"name":"v","profile":"uint8","position":1,)"
      R"("ha_profile":""}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);

  REQUIRE(cmd.hasNnOverride() == true);
  REQUIRE(cmd.getNn().size() == 1);
  REQUIRE(cmd.getNn()[0] == 0x03);

  uint8_t buf[10];
  size_t len = cmd.buildReadCmd(buf, sizeof(buf));
  REQUIRE(len == 5);
  REQUIRE(buf[3] == 0x03);
  REQUIRE(buf[4] == 0x01);
}

TEST_CASE("Command buildWriteCmd derives NN from value", "[Command]") {
  std::string json =
      R"({"key":"32","name":"W","zz":"50","wid":"b5090e3300",)"
      R"("interval":0,"master":false,)"
      R"("fields":[{"name":"v","profile":"data1c_celsius","position":1,)"
      R"("ha_profile":""}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);

  REQUIRE(cmd.hasWriteCmd() == true);

  uint8_t vb[] = {0xaa};
  ebus::Sequence seq = cmd.buildWriteCmd(ebus::ByteView(vb, 1));
  REQUIRE(seq.size() == 8);
  const uint8_t expect[] = {0x50, 0xb5, 0x09, 0x04, 0x0e, 0x33, 0x00, 0xaa};
  for (size_t i = 0; i < sizeof(expect); i++) REQUIRE(seq[i] == expect[i]);
}

TEST_CASE("Command buildWriteCmd is empty for read-only command", "[Command]") {
  std::string json = R"({"key":"01","name":"T","zz":"fe","id":"0700",)"
                     R"("interval":0,"master":true,)"
                     R"("fields":[{"name":"v","profile":"uint8","position":1,)"
                     R"("ha_profile":""}]})";
  JsonReader reader(json);
  Command cmd = Command::fromJson(reader);

  REQUIRE(cmd.hasWriteCmd() == false);
  uint8_t vb[] = {0xaa};
  REQUIRE(cmd.buildWriteCmd(ebus::ByteView(vb, 1)).empty());
}

TEST_CASE("Command legacy read_cmd round-trips byte-exact", "[Command]") {
  SECTION("Derivable NN matches stored NN") {
    std::string json =
        R"({"key":"01","name":"T","read_cmd":"50b504020d00",)"
        R"("interval":0,"master":false,)"
        R"("fields":[{"name":"v","profile":"uint8","position":1,)"
        R"("ha_profile":""}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);

    REQUIRE(cmd.hasNnOverride() == false);
    uint8_t buf[10];
    size_t len = cmd.buildReadCmd(buf, sizeof(buf));
    REQUIRE(len == 6);
    const uint8_t expect[] = {0x50, 0xb5, 0x04, 0x02, 0x0d, 0x00};
    for (size_t i = 0; i < sizeof(expect); i++) REQUIRE(buf[i] == expect[i]);
  }

  SECTION("Divergent NN becomes explicit override") {
    std::string json =
        R"({"key":"01","name":"T","read_cmd":"feb5160301",)"
        R"("interval":0,"master":true,)"
        R"("fields":[{"name":"v","profile":"uint8","position":1,)"
        R"("ha_profile":""}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);

    REQUIRE(cmd.hasNnOverride() == true);
    uint8_t buf[10];
    size_t len = cmd.buildReadCmd(buf, sizeof(buf));
    REQUIRE(len == 5);
    const uint8_t expect[] = {0xfe, 0xb5, 0x16, 0x03, 0x01};
    for (size_t i = 0; i < sizeof(expect); i++) REQUIRE(buf[i] == expect[i]);
  }

  SECTION("No-tail read keeps original NN") {
    std::string json =
        R"({"key":"01","name":"T","read_cmd":"fe070009",)"
        R"("interval":0,"master":true,)"
        R"("fields":[{"name":"v","profile":"data2b_celsius","position":1,)"
        R"("ha_profile":"sensor_temperature"}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);

    REQUIRE(cmd.getId().size() == 2);
    REQUIRE(cmd.hasNnOverride() == true);
    uint8_t buf[10];
    size_t len = cmd.buildReadCmd(buf, sizeof(buf));
    REQUIRE(len == 4);
    const uint8_t expect[] = {0xfe, 0x07, 0x00, 0x09};
    for (size_t i = 0; i < sizeof(expect); i++) REQUIRE(buf[i] == expect[i]);
  }
}

TEST_CASE("Command matches requires id and exact bytes", "[Command]") {
  SECTION("Idless command never matches") {
    std::string json =
        R"({"key":"01","name":"T","zz":"fe","interval":0,"master":true,)"
        R"("fields":[{"name":"v","profile":"uint8","position":1,)"
        R"("ha_profile":""}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);

    uint8_t bytes[] = {0x10, 0xfe, 0x07, 0x00, 0x09};
    REQUIRE(cmd.matches(ebus::ByteView(bytes, sizeof(bytes))) == false);
  }

  SECTION("Exact match including NN byte") {
    std::string json =
        R"({"key":"01","name":"T","read_cmd":"feb5160301",)"
        R"("interval":0,"master":true,)"
        R"("fields":[{"name":"v","profile":"uint8","position":1,)"
        R"("ha_profile":""}]})";
    JsonReader reader(json);
    Command cmd = Command::fromJson(reader);

    uint8_t hit[] = {0x00, 0xfe, 0xb5, 0x16, 0x03, 0x01};
    REQUIRE(cmd.matches(ebus::ByteView(hit, sizeof(hit))) == true);

    uint8_t miss[] = {0x00, 0xfe, 0xb5, 0x16, 0x04, 0x01};
    REQUIRE(cmd.matches(ebus::ByteView(miss, sizeof(miss))) == false);
  }
}

TEST_CASE("Command evaluate accepts compact schema", "[Command]") {
  std::string json =
      R"({"key":"01","name":"T","zz":"fe","id":"0700","wid":"07000e",)"
      R"("interval":0,"master":true,)"
      R"("fields":[{"name":"v","profile":"data2b_celsius","position":1,)"
      R"("ha_profile":"sensor_temperature"}]})";
  JsonReader reader(json);
  REQUIRE(Command::evaluate(reader).empty());

  std::string no_zz =
      R"({"key":"01","name":"T","id":"0700","interval":0,"master":true,)"
      R"("fields":[{"name":"v","profile":"uint8","position":1,)"
      R"("ha_profile":""}]})";
  JsonReader r2(no_zz);
  std::string_view error = Command::evaluate(r2);
  REQUIRE_FALSE(error.empty());
  REQUIRE(error.find("zz") != std::string_view::npos);
}
