// SPDX-License-Identifier: GPL-3.0-or-later
#include <catch2/catch_test_macros.hpp>

#include <string>
#include <vector>

#include "app/bus_segment.hpp"

TEST_CASE("Bus segments preserve raw bytes between SYN delimiters",
          "[bus_segment]") {
  app::BusSegmentAssembler<8> assembler;
  std::vector<std::vector<uint8_t>> segments;
  auto capture = [&](const uint8_t* bytes, size_t size) {
    segments.emplace_back(bytes, bytes + size);
  };
  using Result = decltype(assembler)::Result;

  REQUIRE(assembler.push(0xaa, capture) == Result::none);
  REQUIRE(assembler.push(0xaa, capture) == Result::none);
  for (uint8_t byte : {0x31, 0xa9, 0x01, 0xfe, 0x00}) {
    REQUIRE(assembler.push(byte, capture) == Result::none);
  }
  REQUIRE(segments.empty());
  REQUIRE(assembler.push(0xaa, capture) == Result::segment);
  REQUIRE((segments == std::vector<std::vector<uint8_t>>{{0x31, 0xa9, 0x01,
                                                          0xfe, 0x00}}));
  REQUIRE(assembler.push(0xaa, capture) == Result::none);
  REQUIRE(assembler.push(0x10, capture) == Result::none);
  REQUIRE(assembler.push(0xaa, capture) == Result::segment);
  REQUIRE(segments.back() == std::vector<uint8_t>{0x10});
}

TEST_CASE("Oversized bus segments are discarded until the next SYN",
          "[bus_segment]") {
  app::BusSegmentAssembler<2> assembler;
  std::vector<std::vector<uint8_t>> segments;
  auto capture = [&](const uint8_t* bytes, size_t size) {
    segments.emplace_back(bytes, bytes + size);
  };
  using Result = decltype(assembler)::Result;

  assembler.push(0x01, capture);
  assembler.push(0x02, capture);
  REQUIRE(assembler.push(0xaa, capture) == Result::segment);
  REQUIRE((segments.back() == std::vector<uint8_t>{0x01, 0x02}));
  assembler.push(0x03, capture);
  assembler.push(0x04, capture);
  assembler.push(0x05, capture);
  assembler.push(0x06, capture);
  REQUIRE(assembler.push(0xaa, capture) == Result::overflow);
  REQUIRE(segments.size() == 1);
  assembler.push(0x07, capture);
  REQUIRE(assembler.push(0xaa, capture) == Result::segment);
  REQUIRE(segments.back() == std::vector<uint8_t>{0x07});
}

TEST_CASE("Bus segment hex encoding preserves bytes", "[bus_segment]") {
  const uint8_t bytes[] = {0x00, 0x01, 0xa9, 0xff};
  char payload[2 * sizeof(bytes) + 1];
  app::writeBusSegmentHex(bytes, sizeof(bytes), payload);
  REQUIRE(std::string(payload) == "0001a9ff");
}

TEST_CASE("Maximum-sized bus segments are retained", "[bus_segment]") {
  app::BusSegmentAssembler<app::max_bus_segment_size> assembler;
  size_t captured = 0;
  auto capture = [&](const uint8_t*, size_t size) { captured = size; };
  for (size_t i = 0; i < app::max_bus_segment_size; ++i) {
    assembler.push(0x01, capture);
  }
  REQUIRE(assembler.push(0xaa, capture) == decltype(assembler)::Result::segment);
  REQUIRE(captured == app::max_bus_segment_size);
}
