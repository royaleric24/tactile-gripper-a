// Host test of the production 14-channel electrode+FSR profile.  The real R/C
// to ADC/AIN map is still missing, so the twelve electrode channels must come
// out as null + NO_DATA while the two FSR channels keep streaming.
#include <cstring>

#include "fsr2_config_electrodes12_fsr2.h"
#include "sampler_cases.h"

int main(int argc, char** argv) {
  const bool emit = argc > 1 && std::strcmp(argv[1], "--emit") == 0;
  return run_fsr2_sampler_cases(FSR2_PROFILE, emit);
}
