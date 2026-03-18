#!/usr/bin/env python3
"""
Example daemon agent that continuously polls for events.

This agent runs in daemon mode (long-running background process) with periodic health checks.
The health check endpoint responds to HTTP GET requests on /health.
"""

import json
import os
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check requests."""
    
    def do_GET(self):
        """Handle GET requests for health check."""
        if self.path == "/health":
            response = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": int(time.time() - start_time),
                "polls_processed": poll_counter["count"]
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        return


def poll_worker():
    """Main polling loop that processes events continuously."""
    poll_interval = int(os.getenv("POLL_INTERVAL", "10"))
    log_level = os.getenv("LOG_LEVEL", "INFO")
    
    print(f"[DAEMON] Polling worker started (interval={poll_interval}s)", flush=True)
    
    while True:
        try:
            # Simulate event polling/processing
            poll_counter["count"] += 1
            
            if log_level != "ERROR":
                print(
                    f"[{datetime.utcnow().isoformat()}] Poll #{poll_counter['count']}: "
                    f"Checking for events...",
                    flush=True
                )
            
            # Simulate some work (e.g., checking external service, processing queue)
            time.sleep(0.5)
            
            # Log periodic status
            if poll_counter["count"] % 6 == 0:  # Every 60 seconds if poll_interval=10
                print(
                    f"[DAEMON] Status: {poll_counter['count']} polls processed, "
                    f"uptime: {int(time.time() - start_time)}s",
                    flush=True
                )
            
            time.sleep(poll_interval)
            
        except Exception as e:
            print(f"[ERROR] Polling error: {e}", flush=True)
            time.sleep(poll_interval)


def start_health_server():
    """Start HTTP server for health checks on configured port."""
    port = int(os.getenv("DAEMON_PORT", "5000"))
    
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"[DAEMON] Health check server listening on port {port}", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"[ERROR] Failed to start health check server: {e}", flush=True)
        raise


def main():
    """Main daemon entry point."""
    global start_time
    start_time = time.time()
    
    print("[DAEMON] Agent starting in daemon mode", flush=True)
    print(f"[DAEMON] Process ID: {os.getpid()}", flush=True)
    
    # Start health check server in background thread
    health_thread = threading.Thread(target=start_health_server, daemon=True, name="health-check")
    health_thread.start()
    print("[DAEMON] Health check thread started", flush=True)
    
    # Run polling worker in main thread (blocks until shutdown)
    try:
        poll_worker()
    except KeyboardInterrupt:
        print("\n[DAEMON] Received shutdown signal, cleaning up...", flush=True)
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}", flush=True)
        raise


if __name__ == "__main__":
    start_time = 0
    poll_counter = {"count": 0}
    main()
