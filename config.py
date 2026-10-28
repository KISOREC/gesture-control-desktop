"""Local configuration with conservative defaults."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    local_only: bool = True
    cursor_sensitivity: float = 1.0
    dwell_seconds: float = 0.7
    screen_analysis_interval: float = 0.4
    voice_model_path: str = ""

    @classmethod
    def from_environment(cls) -> "AppConfig":
        sensitivity = float(os.environ.get("GESTURE_CURSOR_SENSITIVITY", "1.0"))
        dwell = float(os.environ.get("GESTURE_DWELL_SECONDS", "0.7"))
        interval = float(os.environ.get("GESTURE_SCREEN_ANALYSIS_INTERVAL", "0.4"))
        if not 0.2 <= sensitivity <= 3.0:
            raise ValueError("GESTURE_CURSOR_SENSITIVITY must be between 0.2 and 3.0")
        if not 0.2 <= dwell <= 5.0:
            raise ValueError("GESTURE_DWELL_SECONDS must be between 0.2 and 5.0")
        if not 0.2 <= interval <= 5.0:
            raise ValueError("GESTURE_SCREEN_ANALYSIS_INTERVAL must be between 0.2 and 5.0")
        return cls(
            cursor_sensitivity=sensitivity,
            dwell_seconds=dwell,
            screen_analysis_interval=interval,
            voice_model_path=os.environ.get("VOSK_MODEL_PATH", ""),
        )
