"""Tests for daemon manager and monitor with docker-proxy security."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from worker.daemon_manager import (
    get_daemon_run_info,
    get_active_daemon_runs,
    update_daemon_run,
    check_container_status,
    perform_health_check,
    should_restart,
    start_daemon_container,
    remove_daemon_container,
    map_storage_path_to_runner_path,
)
from worker.daemon_monitor import monitor_single_daemon, start_daemon_monitor_loop


class TestSecurityModel:
    """Test docker-proxy security restrictions."""
    
    def test_docker_proxy_environment_variables(self):
        """Verify docker-proxy environment variables are configured correctly."""
        import os
        docker_host = os.getenv("DOCKER_HOST")
        # In production this should be tcp://docker-proxy:2375 (restricted)
        # In tests it may be unset, which falls back to local socket
        assert docker_host is None or "docker-proxy" in docker_host or docker_host.startswith("unix:")
    
    def test_daemon_network_isolation(self):
        """Verify daemon containers run on isolated network."""
        import os
        daemon_network = os.getenv("AGENTFLOW_DAEMON_DOCKER_NETWORK", "crucibleaiagents-daemon")
        assert daemon_network == "crucibleaiagents-daemon"


class TestStoragePathMapping:
    """Test storage path mapping to runner paths."""
    
    def test_map_workspace_package_path(self):
        """Test mapping /workspace/package path."""
        result = map_storage_path_to_runner_path("/workspace/package/deployed/pkg1")
        assert result == "/workspace/package/deployed/pkg1"
    
    def test_map_host_package_path(self):
        """Test mapping host package path."""
        result = map_storage_path_to_runner_path("/Users/test/packages/deployed/pkg1")
        assert "/workspace/package/deployed" in result
        assert "pkg1" in result
    
    def test_map_empty_path_raises_error(self):
        """Test that empty path raises ValueError."""
        with pytest.raises(ValueError, match="storage_path is empty"):
            map_storage_path_to_runner_path("")


class TestRestartPolicy:
    """Test restart policy logic."""
    
    def test_always_restart_policy(self):
        """Test 'always' policy always restarts."""
        assert should_restart("always", 0, 0) is True
        assert should_restart("always", 1, 0) is True
        assert should_restart("always", 127, 0) is True
    
    def test_on_failure_restart_policy(self):
        """Test 'on-failure' policy restarts only on non-zero exit."""
        assert should_restart("on-failure", 0, 0) is False
        assert should_restart("on-failure", 1, 0) is True
        assert should_restart("on-failure", 127, 0) is True
    
    def test_never_restart_policy(self):
        """Test 'never' policy never restarts."""
        assert should_restart("never", 0, 0) is False
        assert should_restart("never", 1, 0) is False
    
    def test_max_restart_attempts(self):
        """Test max restart attempts limit."""
        # Even with 'always', should not restart after max attempts
        assert should_restart("always", 0, 5) is False  # max_restarts=5
        assert should_restart("always", 0, 4) is True
    
    def test_unknown_policy_defaults_to_never(self):
        """Test unknown policy defaults to never restart."""
        assert should_restart("unknown", 1, 0) is False


class TestHealthCheck:
    """Test health check functionality."""
    
    def test_health_check_no_port_configured(self):
        """Test health check passes when no port configured."""
        assert perform_health_check(None) is True
        assert perform_health_check(0) is True
    
    @patch('socket.create_connection')
    def test_health_check_socket_success(self, mock_socket):
        """Test successful health check."""
        mock_conn = MagicMock()
        mock_socket.return_value = mock_conn
        
        result = perform_health_check(8000, "/health")
        
        assert result is True
        mock_socket.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('socket.create_connection')
    def test_health_check_socket_timeout(self, mock_socket):
        """Test health check timeout."""
        import socket
        mock_socket.side_effect = socket.timeout()
        
        result = perform_health_check(8000, "/health")
        
        assert result is False
    
    @patch('socket.create_connection')
    def test_health_check_connection_refused(self, mock_socket):
        """Test health check connection refused."""
        import socket
        mock_socket.side_effect = ConnectionRefusedError()
        
        result = perform_health_check(8000, "/health")
        
        assert result is False


class TestContainerStatus:
    """Test container status checking."""
    
    @patch('subprocess.run')
    def test_check_container_running(self, mock_run):
        """Test checking running container status."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"Running":true,"ExitCode":0,"Error":""}'
        )
        
        status = check_container_status("abc123")
        
        assert status is not None
        assert status["running"] is True
        assert status["exit_code"] == 0
    
    @patch('subprocess.run')
    def test_check_container_exited(self, mock_run):
        """Test checking exited container status."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"Running":false,"ExitCode":1,"Error":""}'
        )
        
        status = check_container_status("abc123")
        
        assert status is not None
        assert status["running"] is False
        assert status["exit_code"] == 1
    
    @patch('subprocess.run')
    def test_check_container_not_found(self, mock_run):
        """Test checking non-existent container."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        
        status = check_container_status("doesnotexist")
        
        assert status is None


class TestDaemonMonitor:
    """Test daemon monitor behavior."""
    
    @patch('worker.daemon_manager.check_container_status')
    @patch('worker.daemon_manager.get_daemon_run_info')
    def test_monitor_missing_container_id(self, mock_get_info, mock_check_status):
        """Test monitor marks run failed when container_id missing."""
        # Patch the reference used by daemon_monitor (not daemon_manager) because
        # from-imports bind at import time and patching the origin module has no effect.
        with patch('worker.daemon_monitor.update_daemon_run') as mock_update:
            run = {
                "id": 1,
                "package_id": 10,
                "container_id": None,
                "restart_count": 0,
            }
            
            monitor_single_daemon(run)
            
            # Should update run to failed
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[0][0] == 1  # run_id
            assert "status" in call_args[1] or call_args[1].get("status") == "failed"
    
    @patch('worker.daemon_monitor.check_container_status')
    def test_monitor_container_not_found(self, mock_check_status):
        """Test monitor marks run failed when container not found."""
        mock_check_status.return_value = None
        
        with patch('worker.daemon_monitor.update_daemon_run') as mock_update:
            run = {
                "id": 1,
                "package_id": 10,
                "container_id": "abc123",
                "restart_count": 0,
            }
            
            monitor_single_daemon(run)
            
            # Should query container status
            mock_check_status.assert_called_once_with("abc123")
            # Should mark run failed
            mock_update.assert_called_once()
    
    @patch('worker.daemon_monitor.check_container_status')
    def test_monitor_container_running_healthy(self, mock_check_status):
        """Test monitor updates last_health_check for running container."""
        mock_check_status.return_value = {
            "running": True,
            "exit_code": 0,
        }
        
        with patch('worker.daemon_monitor.perform_health_check', return_value=True):
            with patch('worker.daemon_monitor.update_daemon_run') as mock_update:
                run = {
                    "id": 1,
                    "package_id": 10,
                    "container_id": "abc123",
                    "restart_count": 0,
                    "health_check_config": {"enabled": True, "path": "/health"},
                    "exposed_port": 8000,
                }
                
                monitor_single_daemon(run)
                
                # Should update last_health_check
                mock_update.assert_called_once()

    @patch('worker.daemon_monitor.check_container_status')
    def test_monitor_container_exited_zero_marks_completed(self, mock_check_status):
        """Test clean daemon exit is marked completed when not restarting."""
        mock_check_status.return_value = {
            "running": False,
            "exit_code": 0,
        }

        with patch('worker.daemon_monitor.update_daemon_run') as mock_update:
            run = {
                "id": 42,
                "package_id": 12,
                "container_id": "abc123",
                "restart_count": 0,
                "restart_policy": "never",
            }

            monitor_single_daemon(run)

            mock_update.assert_called_once()
            assert mock_update.call_args[1]["status"] == "completed"
            assert mock_update.call_args[1]["exit_code"] == 0
            assert "completed_at" in mock_update.call_args[1]

    @patch('worker.daemon_monitor.check_container_status')
    def test_monitor_container_exited_nonzero_marks_stopped(self, mock_check_status):
        """Test non-zero daemon exit remains stopped when not restarting."""
        mock_check_status.return_value = {
            "running": False,
            "exit_code": 1,
        }

        with patch('worker.daemon_monitor.update_daemon_run') as mock_update:
            run = {
                "id": 43,
                "package_id": 12,
                "container_id": "abc123",
                "restart_count": 0,
                "restart_policy": "never",
            }

            monitor_single_daemon(run)

            mock_update.assert_called_once()
            assert mock_update.call_args[1]["status"] == "stopped"
            assert mock_update.call_args[1]["exit_code"] == 1


@pytest.mark.integration
class TestDaemonStartup:
    """Integration tests for daemon startup."""
    
    @patch('subprocess.run')
    def test_start_daemon_container_success(self, mock_run):
        """Test successful daemon container startup."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123def456"
        )
        
        run_info = {
            "id": 1,
            "package_id": 10,
            "storage_path": "pkg10",
            "exposed_port": 8000,
            "health_check_config": {},
            "restart_policy": "on-failure",
            "timeout_seconds": 60,
            "secret_env": {},  # pre-loaded so the DB package_secrets query is skipped
        }
        
        with patch.dict('os.environ', {'WORKSPACE_PACKAGE_HOST_PATH': '/tmp/pkg'}):
            container_id, port = start_daemon_container(run_info)
            
            assert container_id == "abc123def456"
            assert port == 8000
            mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_start_daemon_container_failure(self, mock_run):
        """Test daemon container startup failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Docker error: something went wrong"
        )
        
        run_info = {
            "id": 1,
            "package_id": 10,
            "storage_path": "pkg10",
            "exposed_port": 8000,
            "health_check_config": {},
            "restart_policy": "on-failure",
            "secret_env": {},  # pre-loaded so the DB package_secrets query is skipped
        }
        
        with patch.dict('os.environ', {'WORKSPACE_PACKAGE_HOST_PATH': '/tmp/pkg'}):
            with pytest.raises(RuntimeError, match="Failed to start daemon"):
                start_daemon_container(run_info)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
