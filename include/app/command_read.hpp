#pragma once

#include "app/command.hpp"
#include "app/ebus_accessor.hpp"

// Passive read patterns may be incomplete telegrams and must never be sent.
inline bool requestCommandRead(Command& command) {
  if (!command.getActive() || command.getReadCmd().empty()) return false;
  const auto id = getEbusController().enqueue(app::priority::send,
                                             command.getReadCmd());
  if (id == 0) return false;
  command.setPendingReadId(id);
  return true;
}
