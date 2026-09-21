#pragma once

#include <stdbool.h>

int motors_init(void);
bool motors_write(int motor); /* -1: force all low; 0..3: fixed bench duty only. */
