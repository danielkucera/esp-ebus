// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <string>

namespace HttpUtilsTestState {

extern std::string last_warning;
extern std::string last_error;
void clearLoggerMessages();

}  // namespace HttpUtilsTestState
