#!/usr/bin/env python3
"""
Simple test agent that sleeps for 30 seconds.
Used to verify concurrent execution - multiple instances should run in parallel.
"""
import time
import os
from platform_sdk import get_logger

log = get_logger("agent")

def main():
    run_id = os.environ.get("RUN_ID", "unknown")
    log.info(f"[Run {run_id}] Sleep test agent starting...")
    log.info(f"[Run {run_id}] Going to sleep for 30 seconds...")
    
    # Sleep for 30 seconds
    time.sleep(30)
    
    log.info(f"[Run {run_id}] Woke up! Test completed successfully.")
    return 0

if __name__ == "__main__":
    exit(main())
