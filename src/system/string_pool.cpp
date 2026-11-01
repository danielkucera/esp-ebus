// SPDX-License-Identifier: GPL-3.0-or-later
#if defined(EBUS_INTERNAL)
#include "system/string_pool.hpp"

StringPool& StringPool::instance() {
  static StringPool pool;
  return pool;
}

#endif
