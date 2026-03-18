from typing import Optional
from pydantic import BaseModel

class ScheduleConfig(BaseModel):
    schedule_type: str  # 'interval', 'cron', 'at'
    interval_seconds: Optional[int] = None  # For 'interval' type
    cron_expression: Optional[str] = None  # For 'cron' type
    timestamp: Optional[str] = None  # For 'at' type
    timeout_seconds: Optional[int] = None  # Optional timeout for the scheduled run
    enabled: Optional[bool] = True  # Whether the schedule is active or not
