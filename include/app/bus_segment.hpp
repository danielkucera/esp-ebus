// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <ebus/address.hpp>

namespace app {

inline constexpr size_t max_bus_segment_size = 256;

inline void writeBusSegmentHex(const uint8_t* bytes, size_t size, char* out) {
  static constexpr char hex[] = "0123456789abcdef";
  for (size_t i = 0; i < size; ++i) {
    out[2 * i] = hex[bytes[i] >> 4];
    out[2 * i + 1] = hex[bytes[i] & 0x0f];
  }
  out[2 * size] = '\0';
}

template <size_t Capacity>
class BusSegmentAssembler {
 public:
  enum class Result { none, segment, overflow };

  template <typename Consumer>
  Result push(uint8_t byte, Consumer&& consume) {
    if (byte == ebus::Symbols::syn) {
      const Result result = overflow_ ? Result::overflow
                            : size_  ? Result::segment
                                     : Result::none;
      if (result == Result::segment) consume(bytes_.data(), size_);
      size_ = 0;
      overflow_ = false;
      return result;
    }

    if (!overflow_) {
      if (size_ == Capacity) {
        overflow_ = true;
      } else {
        bytes_[size_++] = byte;
      }
    }
    return Result::none;
  }

 private:
  std::array<uint8_t, Capacity> bytes_{};
  size_t size_ = 0;
  bool overflow_ = false;
};

}  // namespace app
