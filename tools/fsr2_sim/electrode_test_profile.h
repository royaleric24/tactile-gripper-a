// TEST-ONLY synthetic electrode profile.
//
// The real R/C to ADS1220 AIN assignment is still missing (the operator harness
// record has not been filled in), so nothing here is a wiring claim.  This table
// exists only to exercise the mapped-electrode code path in host tests and to
// produce a fixture that shows what a complete mapping will look like once the
// real numbers arrive.
//
// SIM_SYNTHETIC_MAPPING is deliberately not one of the firmware's mapping
// status strings, so this header can never be mistaken for a production config.
#pragma once

#include <stdint.h>

#include "fsr2.h"

namespace fsr2sim {

static const uint8_t kPinsMiso[4] = {34, 35, 26, 33};
static const uint8_t kPinsCs[4] = {21, 22, 5, 32};

// R1..R6 then C1..C6.  Row electrodes on ADC1/ADC2, column electrodes on
// ADC2/ADC3 AINs; ADC4 stays free (no FSR in this test).
static const Fsr2ChannelConfig kChannels[12] = {
    {0, 0, 8, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 1, "R1"},
    {0, 1, 9, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 2, "R2"},
    {0, 2, 10, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 3, "R3"},
    {0, 3, 11, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 4, "R4"},
    {1, 0, 8, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 5, "R5"},
    {1, 1, 9, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 6, "R6"},
    {1, 2, 10, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 1, "C1"},
    {1, 3, 11, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 2, "C2"},
    {2, 0, 8, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 3, "C3"},
    {2, 1, 9, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 4, "C4"},
    {2, 2, 10, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 5, "C5"},
    {2, 3, 11, FSR2_KIND_ELECTRODE, FSR2_ROLE_COLUMN, 6, "C6"},
};

static const Fsr2Profile kProfile = {
    "tactile-esp32-01",
    "tactile-sim-synthetic-0.0.0",
    "MATRIX_ELECTRODES_12",
    "OFFLINE_ELECTRODE_READ",
    "AVDD_AVSS",
    921600UL,
    18,
    23,
    4,
    12,
    kPinsMiso,
    kPinsCs,
    12,
    6,
    6,
    "SIM_SYNTHETIC_MAPPING",
    "PULLDOWN_10K_TO_GND",
    "PULLUP_1K_TO_3V3",
    0,
    nullptr,
    0,
    0,
    kChannels,
    3,
    4,
    330,
    4500,
    1,
    0,
    1,
    8192,
    512,
    1000,
    32,
    3,
    500,
};

}  // namespace fsr2sim
