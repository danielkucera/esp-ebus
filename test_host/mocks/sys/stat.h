#pragma once

// Host persistence tests write real files. Use the host ABI and errno rather
// than a fake stat() that always fails and leaves errno from an earlier call.
#include_next <sys/stat.h>
