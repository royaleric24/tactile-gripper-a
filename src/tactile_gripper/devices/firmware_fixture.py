"""Read-only firmware-generated JSONL sources for the offline Dashboard."""

from .sensor import PROJECT_ROOT, SensorAdapter
from ..sources import DataSource

FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "fsr2"

FIXTURE_STREAMS = {
    "fsr1": ("hello_fsr1", "sample_fsr1_valid"),
    "fsr1-adc4-fault": ("hello_fsr1", "sample_fsr1_valid", "sample_fsr1_no_adc4", "status_fsr1_no_adc4"),
    "electrodes12-fsr1": ("hello_electrodes12_fsr1_unmapped", "sample_electrodes12_fsr1_unmapped"),
    "electrodes12-fsr1-adc4-fault": ("hello_electrodes12_fsr1_unmapped", "sample_electrodes12_fsr1_unmapped",
                                   "sample_electrodes12_fsr1_no_adc4", "status_electrodes12_fsr1_no_adc4"),
    "fsr": ("hello_fsr_only", "sample_fsr_only_valid"),
    "fsr-adc4-fault": ("hello_fsr_only", "sample_fsr_only_valid",
                       "sample_fsr_only_no_adc4", "status_fsr_only_no_adc4"),
    "electrodes12": ("hello_electrodes12_mapped_synthetic", "sample_electrodes12_mapped_synthetic"),
    "electrodes12-partial": ("hello_electrodes12_mapped_synthetic", "sample_electrodes12_mapped_synthetic",
                             "sample_electrodes12_mapped_adc_absent", "status_electrodes12_mapped_adc_absent"),
    "electrodes12-fsr2": ("hello_electrodes12_fsr2_unmapped", "sample_electrodes12_fsr2_unmapped"),
    "electrodes12-fsr2-adc4-fault": ("hello_electrodes12_fsr2_unmapped", "sample_electrodes12_fsr2_unmapped",
                                   "sample_electrodes12_fsr2_fsr_absent", "status_electrodes12_fsr2_fsr_absent"),
}


class FirmwareFixtureTransport:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.offset = 0
        self.lines = [(FIXTURE_ROOT / (name + ".json")).read_bytes() for name in FIXTURE_STREAMS[scenario]]

    @property
    def at_end(self) -> bool:
        return self.offset >= len(self.lines)

    def connect(self) -> None:
        self.offset = 0

    def close(self) -> None:
        pass

    def readline(self, timeout_s: float) -> bytes | None:
        if self.at_end:
            return None
        self.offset += 1
        return self.lines[self.offset - 1]


def firmware_fixture_adapter(scenario: str, **kwargs) -> SensorAdapter:
    return SensorAdapter(FirmwareFixtureTransport(scenario), None, source=DataSource.SIMULATION,
                         strict_v2=True, max_line_bytes=8192, **kwargs)
