#define private public
#define protected public
#include <catch2/catch_test_macros.hpp>
#include <string>

#include "api/values_api.hpp"
#include "app/ebus_test_helpers.hpp"
#include "app/command.hpp"
#include "app/command_manager.hpp"
#include "app/ebus_test_helpers.hpp"
#undef private
#undef protected

namespace {

std::string makeCommandJson() {
  return R"({
    "key":"01",
    "name":"Outside_Temperature",
    "read_cmd":"50b509030d3300",
    "write_cmd":"50b509050e3300",
    "interval":60,
    "master":false,
    "fields":[
      {"name":"value","profile":"data2b_celsius","position":1,"ha_profile":"sensor_temperature"}
    ]
  })";
}

void insertTestCommand() {
  command_manager.wipeCommands();
  const std::string command_json = makeCommandJson();
  ebus::detail::JsonReader reader(command_json);
  Command command = Command::fromJson(reader);
  command_manager.insertCommand(std::move(command));
}

}  // namespace

TEST_CASE("ValuesApi serves the values page", "[values_api]") {
  command_manager.wipeCommands();
  ValuesApi api(command_manager);
  httpd_req_t req{};

  REQUIRE(ValuesApi::handleValuesPage(&req) == ESP_OK);
  REQUIRE(req.status == "200 OK");
  REQUIRE(req.content_type == "text/html");
  REQUIRE(req.final_body == "<html><body>values</body></html>");
}

TEST_CASE("ValuesApi reads and writes by key", "[values_api]") {
  REQUIRE(configureHostEbusController());
  insertTestCommand();
  REQUIRE(command_manager.findCommand("01") != nullptr);

  ValuesApi api(command_manager);

  httpd_req_t read_req{};
  read_req.body = R"({"key":"01"})";
  read_req.content_len = static_cast<int>(read_req.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&read_req) == ESP_OK);
  REQUIRE(read_req.status == "200 OK");
  REQUIRE(command_manager.findCommand("01")->getPendingReadId() != 0);
  REQUIRE(read_req.content_type == "application/json;charset=utf-8");
  REQUIRE(read_req.final_body.find(R"("id":"read")") != std::string::npos);
  REQUIRE(read_req.final_body.find(R"("status":"requested")") !=
          std::string::npos);

  // A one-shot reply has no poll_id; it must still update the active command.
  const uint8_t response[] = {2, 0, 21};  // DATA2B: 21 degrees
  ebus::ProtocolInfo info{};
  info.session_id = command_manager.findCommand("01")->getPendingReadId();
  info.slave_view = ebus::ByteView(response, sizeof(response));
  command_manager.updateData(info);
  REQUIRE(command_manager.findCommand("01")->getData().size() == 2);
  REQUIRE(command_manager.findCommand("01")->getData()[1] == 21);
  REQUIRE(command_manager.findCommand("01")->getPendingReadId() == 0);

  httpd_req_t write_req{};
  write_req.body = R"({"key":"01","value":12.5})";
  write_req.content_len = static_cast<int>(write_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&write_req) == ESP_OK);
  REQUIRE(write_req.status == "200 OK");
  REQUIRE(write_req.final_body.find(R"("id":"write")") != std::string::npos);
  REQUIRE(write_req.final_body.find(R"("status":"successful")") !=
          std::string::npos);

  auto* command = command_manager.findCommand("01");
  REQUIRE(command->getWriteSessionId() != 0);
  REQUIRE(command->getPendingReadId() == 0);
  ebus::ProtocolInfo write_result{};
  write_result.session_id = command->getWriteSessionId();
  command_manager.handleWriteResult(write_result);
  REQUIRE(command->getWriteSessionId() == 0);
  REQUIRE(command->getPendingReadId() != 0);

  httpd_req_t list_req{};
  REQUIRE(ValuesApi::handleValues(&list_req) == ESP_OK);
  REQUIRE(list_req.content_type == "application/json;charset=utf-8");
  std::string values_body;
  for (const auto& chunk : list_req.chunks) values_body += chunk;
  REQUIRE(values_body.find(R"("key":"01")") != std::string::npos);
  REQUIRE(values_body.find(R"("name":"Outside_Temperature")") !=
          std::string::npos);
  REQUIRE(list_req.chunks.back().empty());

  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi rejects unknown keys", "[values_api]") {
  command_manager.wipeCommands();
  ValuesApi api(command_manager);

  httpd_req_t read_req{};
  read_req.body = R"({"key":"missing"})";
  read_req.content_len = static_cast<int>(read_req.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&read_req) == ESP_OK);
  REQUIRE(read_req.status == "404 Not Found");
  REQUIRE(read_req.final_body.find(R"("id":"read")") != std::string::npos);
  REQUIRE(read_req.final_body.find("Key 'missing' not found") !=
          std::string::npos);

  httpd_req_t write_req{};
  write_req.body = R"({"key":"missing","value":12.5})";
  write_req.content_len = static_cast<int>(write_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&write_req) == ESP_OK);
  REQUIRE(write_req.status == "404 Not Found");
  REQUIRE(write_req.final_body.find(R"("id":"write")") != std::string::npos);
  REQUIRE(write_req.final_body.find("Key 'missing' not found") !=
          std::string::npos);
}

TEST_CASE("ValuesApi rejects malformed and invalid writes", "[values_api]") {
  insertTestCommand();
  ValuesApi api(command_manager);

  httpd_req_t malformed_req{};
  malformed_req.body = R"({"key":"01","value":)";
  malformed_req.content_len = static_cast<int>(malformed_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&malformed_req) == ESP_OK);
  REQUIRE(malformed_req.status == "400 Bad Request");
  REQUIRE(malformed_req.final_body.find(R"("status":"failed")") !=
          std::string::npos);

  httpd_req_t invalid_value_req{};
  invalid_value_req.body = R"({"key":"01","value":"not-a-number"})";
  invalid_value_req.content_len =
      static_cast<int>(invalid_value_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&invalid_value_req) == ESP_OK);
  REQUIRE(invalid_value_req.status == "400 Bad Request");
  REQUIRE(invalid_value_req.final_body.find(R"("id":"write")") !=
          std::string::npos);
  REQUIRE(invalid_value_req.final_body.find("Invalid value for key '01'") !=
          std::string::npos);

  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi rejects sending passive match patterns", "[values_api]") {
  command_manager.wipeCommands();
  const std::string json = R"({"key":"passive","name":"Room","read_cmd":"51501407","interval":0,"master":true,"fields":[{"name":"value","profile":"data2b_celsius","position":4}]})";
  ebus::detail::JsonReader reader(json);
  command_manager.insertCommand(Command::fromJson(reader));
  ValuesApi api(command_manager);
  httpd_req_t req{};
  req.body = R"({"key":"passive"})";
  req.content_len = static_cast<int>(req.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&req) == ESP_OK);
  REQUIRE(req.status == "400 Bad Request");
  REQUIRE(command_manager.findCommand("passive")->getPendingReadId() == 0);
  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi rejects writes when the bus queue is full", "[values_api]") {
  insertTestCommand();
  auto& controller = getEbusController();
  auto config = getEbusConfig();
  config.bus.device = "/dev/null";
  REQUIRE(controller.configure(config));
  struct ResetController {
    ebus::Controller& controller;
    ebus::EbusConfig config;
    ~ResetController() { controller.configure(config); }
  } reset{controller, config};

  // The controller is not started, so queued requests cannot be drained.
  const ebus::Sequence message{0x50, 0xb5, 0x09, 0x04, 0x0e, 0x33, 0x00, 0x00};
  bool full = false;
  for (unsigned i = 0; i < 1024; ++i) {
    if (controller.enqueue(app::priority::send, message) == 0) {
      full = true;
      break;
    }
  }
  REQUIRE(full);
  auto* command = command_manager.findCommand("01");
  REQUIRE(command != nullptr);
  command->setLast(123);

  ValuesApi api(command_manager);
  httpd_req_t req{};
  req.body = R"({"key":"01","value":12.5})";
  req.content_len = static_cast<int>(req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&req) == ESP_OK);
  REQUIRE(req.status == "503 Service Unavailable");
  REQUIRE(req.final_body.find("Unable to queue write command") != std::string::npos);
  REQUIRE(req.final_body.find(R"("status":"successful")") == std::string::npos);
  REQUIRE(command->getLast() == 123);
  REQUIRE(command->getWriteSessionId() == 0);
  REQUIRE(command->getPendingReadId() == 0);
  command_manager.wipeCommands();
}
