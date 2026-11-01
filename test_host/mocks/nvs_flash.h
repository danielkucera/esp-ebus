// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Host mock for ESP-IDF nvs_flash.h.

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t nvs_flash_init(void);
esp_err_t nvs_flash_erase(void);

#ifdef __cplusplus
}
#endif
