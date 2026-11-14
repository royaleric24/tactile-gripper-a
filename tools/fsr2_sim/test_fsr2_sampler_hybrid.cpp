// Host test of the HYBRID_6X6_FSR2 sampler against the four-device simulation.
// The simulation does not model the column/row cross-coupling, so this checks
// channel mapping, framing and validity, not the matrix electrical path.
#include <cstring>

#include "fsr2_config_hybrid.h"
#include "sampler_cases.h"

int main(int argc, char** argv) {
  const bool emit = argc > 1 && std::strcmp(argv[1], "--emit") == 0;
  return run_fsr2_sampler_cases(FSR2_PROFILE, emit);
}
