#include <cstring>

#include "fsr2_config_electrodes12_fsr1.h"
#include "sampler_cases.h"

int main(int argc, char** argv) {
  const bool emit = argc > 1 && std::strcmp(argv[1], "--emit") == 0;
  return run_fsr2_sampler_cases(FSR2_PROFILE, emit);
}
