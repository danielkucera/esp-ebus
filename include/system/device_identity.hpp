// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Calculates the 6-hex-digit ID from the WiFi STA MAC eFuse.
// Must be called once during early startup.
void calcUniqueId();

// Null-terminated 6-char ID, valid after calcUniqueId().
const char* getUniqueId();
