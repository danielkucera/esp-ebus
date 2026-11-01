// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>

namespace app::detail {

// Monotonic deadlines: bus notifications must not accelerate health sampling.
class MonitorSchedule {
 public:
  uint32_t waitMs(uint64_t now_us) const {
    if (now_us >= next_status_us_) return 0;
    return static_cast<uint32_t>((next_status_us_ - now_us + 999) / 1000);
  }

  bool statusDue(uint64_t now_us) {
    return advance(now_us, next_status_us_, 30ULL * 1000000);
  }
  bool summaryDue(uint64_t now_us) {
    return advance(now_us, next_summary_us_, 300ULL * 1000000);
  }
  bool trendDue(uint64_t now_us) {
    return advance(now_us, next_trend_us_, 3600ULL * 1000000);
  }

 private:
  static bool advance(uint64_t now_us, uint64_t& next_us, uint64_t period_us) {
    if (now_us < next_us) return false;
    next_us = now_us + period_us;
    return true;
  }

  uint64_t next_status_us_ = 0;
  uint64_t next_summary_us_ = 0;
  uint64_t next_trend_us_ = 0;
};

}  // namespace app::detail
