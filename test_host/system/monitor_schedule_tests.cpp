// SPDX-License-Identifier: GPL-3.0-or-later
#include <catch2/catch_test_macros.hpp>
#include "system/detail/monitor_schedule.hpp"

TEST_CASE("Bus notifications do not accelerate health or heap trend sampling", "[monitor]") {
  app::detail::MonitorSchedule schedule;
  REQUIRE(schedule.statusDue(0));
  REQUIRE(schedule.summaryDue(0));
  REQUIRE(schedule.trendDue(0));
  REQUIRE(schedule.waitMs(0) == 30000);
  for (uint64_t now = 1; now < 30000000; now += 500) {
    REQUIRE_FALSE(schedule.statusDue(now));
    REQUIRE_FALSE(schedule.summaryDue(now));
    REQUIRE_FALSE(schedule.trendDue(now));
  }
  REQUIRE(schedule.statusDue(30000000));
  REQUIRE_FALSE(schedule.statusDue(30000000));
  REQUIRE(schedule.summaryDue(300000000));
  REQUIRE_FALSE(schedule.trendDue(3599999999ULL));
  REQUIRE(schedule.trendDue(3600000000ULL));
}

TEST_CASE("Delayed monitoring skips missed intervals and handles long uptimes", "[monitor]") {
  app::detail::MonitorSchedule schedule;
  constexpr uint64_t now = 100ULL * 24 * 3600 * 1000000;
  REQUIRE(schedule.statusDue(now));
  REQUIRE(schedule.summaryDue(now));
  REQUIRE(schedule.trendDue(now));
  REQUIRE_FALSE(schedule.statusDue(now + 1));
  REQUIRE(schedule.waitMs(now + 1) == 30000);
  REQUIRE(schedule.waitMs(now + 29999999) == 1);
  REQUIRE(schedule.waitMs(now + 30000000) == 0);
  REQUIRE(schedule.statusDue(now + 30000000));
}
