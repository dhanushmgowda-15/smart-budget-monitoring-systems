"""Unified runner for SpendSense.

Starts both the FastAPI backend and the Streamlit frontend with a single command:
    python run.py

Features:
  - Robust port and health check so frontend doesn't start before backend is ready
  - Graceful shutdown of both backend and frontend processes on Ctrl+C / SIGINT
  - Clear console feedback with direct URLs to frontend and API docs
"""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from typing import List

# Ensure Windows consoles support UTF-8 characters cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether a TCP port is currently open and accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def wait_for_backend(url: str = "http://127.0.0.1:8000/health", timeout_seconds: float = 15.0) -> bool:
    """Polls the backend health check endpoint until it responds or times out."""
    start_time = time.time()
    print("⏳ Waiting for SpendSense backend API to become ready...", flush=True)

    while time.time() - start_time < timeout_seconds:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)

    return False


def main():
    """Main launcher starting FastAPI backend and Streamlit frontend."""
    # Ensure current directory is in PYTHONPATH
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.environ["PYTHONPATH"] = project_root

    processes: List[subprocess.Popen] = []

    def shutdown(signum=None, frame=None):
        """Terminates all running subprocesses gracefully."""
        print("\n🛑 Shutting down SpendSense...", flush=True)
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print("✅ Shutdown complete.", flush=True)
        sys.exit(0)

    # Register signal handlers for clean exit
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Check if port 8000 or 8501 is already in use
    if is_port_in_use(8000):
        print("⚠️ Port 8000 is already in use. Checking if backend is already running...", flush=True)
        if not wait_for_backend(timeout_seconds=2.0):
            print("❌ Port 8000 is occupied by an unknown process. Please free port 8000 before running.", flush=True)
            sys.exit(1)
        backend_proc = None
    else:
        # Start FastAPI backend with uvicorn
        backend_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
        print("🚀 Starting FastAPI backend on http://127.0.0.1:8000...", flush=True)
        backend_proc = subprocess.Popen(backend_cmd, cwd=project_root)
        processes.append(backend_proc)

        # Wait for backend to be ready
        if not wait_for_backend():
            print("❌ Backend failed to start within timeout. Aborting.", flush=True)
            shutdown()

    print("\n" + "=" * 70)
    print("✨ SpendSense Backend is LIVE!")
    print("   👉 API Base:          http://localhost:8000")
    print("   👉 Interactive Docs:  http://localhost:8000/docs")
    print("=" * 70 + "\n", flush=True)

    # Start Streamlit frontend
    frontend_script = os.path.join(project_root, "frontend", "app.py")
    frontend_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        frontend_script,
        "--server.port",
        "8501",
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]

    print("🚀 Starting Streamlit frontend on http://127.0.0.1:8501...", flush=True)
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=project_root)
    processes.append(frontend_proc)

    print("\n" + "=" * 70)
    print("🎉 SpendSense Web Application is ready!")
    print("   👉 Access Web App:    http://localhost:8501")
    print("   Press Ctrl+C to stop both servers.")
    print("=" * 70 + "\n", flush=True)

    # Monitor processes until one exits or user interrupts
    try:
        while True:
            for p in processes:
                if p.poll() is not None:
                    print(f"⚠️ A sub-process exited unexpectedly with code {p.returncode}.", flush=True)
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
