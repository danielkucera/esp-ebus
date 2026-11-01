#include <catch2/catch_test_macros.hpp>
#include <string>
#include <thread>
#include <vector>

#include "system/string_pool.hpp"

// NOTE: StringPool is a process-wide singleton, so this is a single ordered
// test case using unique keys to stay independent of execution order.
TEST_CASE("StringPool interns and looks up strings", "[string_pool]") {
  StringPool& pool = StringPool::instance();
  const uint8_t base = pool.count();

  const uint8_t id1 = pool.intern("__test_key_alpha__");
  const uint8_t id2 = pool.intern("__test_key_beta__");
  REQUIRE(id1 != 0);
  REQUIRE(id2 != 0);
  REQUIRE(id1 != id2);

  // Interning the same string returns the existing id.
  REQUIRE(pool.intern("__test_key_alpha__") == id1);

  REQUIRE(std::string(pool.lookup(id1)) == "__test_key_alpha__");
  REQUIRE(std::string(pool.lookup(id2)) == "__test_key_beta__");
  REQUIRE(pool.count() == static_cast<uint8_t>(base + 2));

  // Empty and out-of-range lookups are safe.
  REQUIRE(pool.intern("") == 0);
  REQUIRE(pool.lookup(0).empty());
}

TEST_CASE("StringPool keeps existing IDs valid when its index capacity is full", "[string_pool]") {
  StringPool pool;
  for (unsigned i = 0; i < 255; ++i) {
    REQUIRE(pool.intern(std::to_string(i)) == i + 1);
  }
  REQUIRE(pool.intern("overflow") == 0);
  REQUIRE(pool.count() == 255);
  for (unsigned i = 0; i < 255; ++i) {
    REQUIRE(pool.lookup(static_cast<uint8_t>(i + 1)) == std::to_string(i));
    REQUIRE(pool.intern(std::to_string(i)) == i + 1);
  }
}

TEST_CASE("StringPool rejects oversized names and preserves entries when bytes run out", "[string_pool]") {
  StringPool pool;
  REQUIRE(pool.intern(std::string(256, 'x')) == 0);
  for (int i = 0; i < 8; ++i) REQUIRE(pool.intern(std::string(255, 'a' + i)) != 0);
  REQUIRE(pool.intern("no room") == 0);
  REQUIRE(pool.intern(std::string(255, 'a')) == 1);
  REQUIRE(pool.lookup(1) == std::string(255, 'a'));
}

TEST_CASE("StringPool concurrently interns shared names without duplicate IDs", "[string_pool]") {
  StringPool pool;
  std::vector<std::thread> workers;
  for (int i = 0; i < 8; ++i) {
    workers.emplace_back([&] {
      for (int repeat = 0; repeat < 100; ++repeat) {
        for (int key = 0; key < 20; ++key) pool.intern(std::to_string(key));
      }
    });
  }
  for (auto& worker : workers) worker.join();
  REQUIRE(pool.count() == 20);
  for (int key = 0; key < 20; ++key) {
    const auto id = pool.intern(std::to_string(key));
    REQUIRE(id != 0);
    REQUIRE(pool.lookup(id) == std::to_string(key));
  }
}
