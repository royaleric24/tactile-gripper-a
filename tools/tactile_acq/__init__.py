"""Real ADS1220 tactile acquisition, validation and monitoring."""
from .protocol import (
    ADC_MAX,
    ADC_MIN,
    CHANNEL_COUNT,
    CHANNEL_FLAGS,
    FrameValidationError,
    ProtocolError,
    SampleFrame,
    channel_label,
    flag_names,
    parse_message,
)

__version__ = "0.1.0"
