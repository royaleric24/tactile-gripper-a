"""Generate firmware constants from the checked serial-only configuration."""
from pathlib import Path
import json
c=json.loads(Path('config/serial_test.json').read_text())
Path('firmware/serial_test/serial_config.h').write_text('#pragma once\n'+f'#define TEST_BAUD {c["baudrate"]}\n#define TEST_MAX_LINE {c["max_request_bytes"]}\n#define TEST_PARTIAL_TIMEOUT {c["partial_timeout_ms"]}\n#define TEST_FW_VERSION "{c["firmware_version"]}"\n')
