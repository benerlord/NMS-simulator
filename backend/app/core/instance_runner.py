import subprocess
import sys
import time
from threading import Lock, Thread

from app.db.connection import connect


def _update_status(inst_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE mock_instances SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, inst_id),
        )


class InstanceRunner:
    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}
        self._restart_counts: dict[str, list[float]] = {}
        self._lock = Lock()
        self._stop_monitor = False

    def sync_all(self):
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, port, topology_id FROM mock_instances WHERE enabled = 1"
            ).fetchall()
        for r in rows:
            self.start_instance(r["id"], r["port"], r["topology_id"])

    def start_instance(self, inst_id: str, port: int, topology_id: str):
        with self._lock:
            if inst_id in self._processes:
                return
            _update_status(inst_id, "starting")
            try:
                kwargs = {}
                if sys.platform == 'win32':
                    kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                proc = subprocess.Popen(
                    [
                        sys.executable, "-m", "app.mock.instance_app",
                        "--topology-id", topology_id,
                        "--port", str(port),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs,
                )
                self._processes[inst_id] = proc
                _update_status(inst_id, "running")
            except Exception:
                _update_status(inst_id, "error")

    def stop_instance(self, inst_id: str):
        with self._lock:
            proc = self._processes.pop(inst_id, None)
            if proc:
                proc.kill()
                proc.wait(timeout=3)
            _update_status(inst_id, "stopped")

    def restart_instance(self, inst_id: str, port: int, topology_id: str):
        self.stop_instance(inst_id)
        self.start_instance(inst_id, port, topology_id)

    def shutdown_all(self):
        with self._lock:
            for inst_id in list(self._processes.keys()):
                self.stop_instance(inst_id)
        self._stop_monitor = True

    def _check_and_restart(self):
        with self._lock:
            for inst_id, proc in list(self._processes.items()):
                if proc.poll() is None:
                    continue
                # 限流：1 分钟内超过 3 次重启则标记 error
                now = time.time()
                self._restart_counts.setdefault(inst_id, []).append(now)
                self._restart_counts[inst_id] = [
                    t for t in self._restart_counts[inst_id] if now - t < 60
                ]
                if len(self._restart_counts[inst_id]) > 3:
                    _update_status(inst_id, "error")
                    self._processes.pop(inst_id, None)
                    continue
                self._processes.pop(inst_id, None)
                # 从 DB 读取最新配置后重启
                with connect() as conn:
                    row = conn.execute(
                        "SELECT port, topology_id FROM mock_instances WHERE id = ? AND enabled = 1",
                        (inst_id,),
                    ).fetchone()
                if row:
                    self.start_instance(inst_id, row["port"], row["topology_id"])

    def start_monitor(self):
        """后台线程：每 15 秒检查子进程健康状态"""
        def _loop():
            while not self._stop_monitor:
                time.sleep(15)
                self._check_and_restart()
        t = Thread(target=_loop, daemon=True)
        t.start()
