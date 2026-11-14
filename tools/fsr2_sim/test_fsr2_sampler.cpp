// Host test of the FSR_ONLY sampler against the four-device simulation.
#include <cstring>

#include "fsr2_config.h"
#include "sampler_cases.h"

int main(int argc, char** argv) {
  const bool emit = argc > 1 && std::strcmp(argv[1], "--emit") == 0;
  return run_fsr2_sampler_cases(FSR2_PROFILE, emit);
}
