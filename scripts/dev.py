"""Start both local processes and forward shutdown to their process groups."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
api_port = int(os.getenv("API_PORT", "8000"))
frontend_port = int(os.getenv("FRONTEND_PORT", "5173"))

for port in (api_port, frontend_port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            sys.exit(f"端口 {port} 已占用，请停止旧服务或在 .env 中更换端口。")

processes = []


def shutdown(*_):
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)
try:
    processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                      "--port", str(api_port)], cwd=ROOT, start_new_session=True))
    processes.append(subprocess.Popen(["npm", "run", "dev", "--", "--port", str(frontend_port)],
                                      cwd=ROOT / "frontend", start_new_session=True))
    print(f"\n研究工作台 http://localhost:{frontend_port}\n接口文档 http://localhost:{api_port}/docs\nCtrl+C 停止全部服务。\n", flush=True)
    while all(p.poll() is None for p in processes):
        time.sleep(0.5)
finally:
    shutdown()
