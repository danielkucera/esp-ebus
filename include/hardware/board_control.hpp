// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

void configureGpioInputPullup(int pin);

void disableTX();
void enableTX();

void restart();
void checkReset();
