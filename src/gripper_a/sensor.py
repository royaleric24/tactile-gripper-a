"""Strict offline validation profile; not yet agreed with group C."""
import json
import math

def number(value):
    return type(value) in (int, float) and math.isfinite(value)

def validate(frame, qualities):
    if not isinstance(frame, dict): raise ValueError("not_object")
    required = {"timestamp_ms", "material", "frame_id", "channels", "valid_mask", "contact_score", "valid", "quality_flag"}
    if not required <= frame.keys(): raise ValueError("missing_fields")
    for key in ("timestamp_ms", "frame_id"):
        if type(frame[key]) is not int or frame[key] < 0: raise ValueError(key)
    if frame["material"] not in ("FABRIC", "SILICONE"): raise ValueError("material")
    if not isinstance(frame["channels"], list) or len(frame["channels"]) != 16 or not all(number(x) for x in frame["channels"]): raise ValueError("channels")
    if not isinstance(frame["valid_mask"], list) or len(frame["valid_mask"]) != 16 or not all(type(x) is bool and x for x in frame["valid_mask"]): raise ValueError("invalid_mask")
    if frame["valid"] is not True: raise ValueError("invalid_frame")
    if not isinstance(frame["quality_flag"], str) or frame["quality_flag"] not in qualities: raise ValueError("quality")
    if not number(frame["contact_score"]): raise ValueError("score")
    return frame

def decode_line(raw, max_bytes, qualities):
    if not isinstance(raw, bytes) or len(raw) > max_bytes or not raw.endswith(b"\n"): raise ValueError("framing")
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise ValueError("duplicate_key")
            result[k] = v
        return result
    try: frame = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc: raise ValueError("encoding") from exc
    return validate(frame, qualities)
