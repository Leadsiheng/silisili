from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    # Experimental development defaults, not approved production policy.
    manual_version: str = "dev-1"
    stranger_daily_limit: int = 5
    stranger_max_chars: int = 150  # Unicode code points, not UTF-8 bytes.
    message_max_chars: int = 4000
    baseline_days: int = 14
    timezone: str = "Asia/Shanghai"
    trust_required: bool = False
    coins_enabled: bool = False  # Economics must be approved before enabling.
    rename_cooldown_days: int = 7
    image_max_bytes: int = 10 * 1024 * 1024
    video_max_bytes: int = 100 * 1024 * 1024
    account_storage_bytes: int = 500 * 1024 * 1024
