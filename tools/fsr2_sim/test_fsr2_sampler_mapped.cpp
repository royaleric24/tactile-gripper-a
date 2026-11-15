// Host test of a fully mapped 12-electrode table.  The mapping in
// electrode_test_profile.h is SYNTHETIC and exists only to exercise the
// mapped-read path; it is not the real harness record.
#include <cstring>

#include "electrode_test_profile.h"
#include "sampler_cases.h"

int main(int argc, char** argv) {
  const bool emit = argc > 1 && std::strcmp(argv[1], "--emit") == 0;
  return run_fsr2_sampler_cases(fsr2sim::kProfile, emit);
}
