# ============================================================================
# monitor.py - Module giám sát log file theo thời gian thực
# ============================================================================
# Sử dụng kỹ thuật "tail -f" thuần Python: mở file, seek đến cuối,
# rồi liên tục đọc dòng mới. Mỗi dòng log mới được đẩy vào queue
# để các module khác xử lý (producer-consumer pattern).
# ============================================================================

import os
import time
import threading
from queue import Queue, Full
from rich.console import Console

from active_defense.config import AUTH_LOG, NGINX_LOG, POLL_INTERVAL

console = Console()


class LogMonitor:
    """
    Lớp giám sát file log theo thời gian thực (real-time).

    Nguyên lý hoạt động:
    - Mỗi file log được theo dõi bởi một thread riêng biệt (đa luồng).
    - Thread mở file, nhảy đến cuối (seek END) rồi liên tục poll dòng mới.
    - Dòng log mới được đóng gói thành tuple (log_type, line) và đẩy vào
      một Queue chung để Detector xử lý.
    - Hỗ trợ xử lý file bị rotate (logrotate): khi file bị truncate hoặc
      thay thế, monitor sẽ tự động mở lại file từ đầu.

    Attributes:
        log_queue (Queue): Hàng đợi chung chứa các dòng log mới.
        _stop_event (threading.Event): Cờ tín hiệu để dừng tất cả thread.
        _threads (list): Danh sách các thread đang chạy.
    """

    def __init__(self, log_queue: Queue):
        """
        Khởi tạo LogMonitor.

        Args:
            log_queue: Queue dùng chung giữa Monitor và Detector.
                       Monitor sẽ put() dòng log, Detector sẽ get().
        """
        self.log_queue = log_queue
        self._stop_event = threading.Event()
        self._threads = []

    def start(self):
        """
        Bắt đầu giám sát tất cả file log.

        Tạo một thread cho mỗi file log và bắt đầu chạy.
        - Thread "auth": giám sát auth.log (sự kiện SSH)
        - Thread "nginx": giám sát nginx access.log (sự kiện HTTP)
        """
        # Danh sách (loại_log, đường_dẫn_file) cần giám sát
        log_files = [
            ("auth", AUTH_LOG),
            ("nginx", NGINX_LOG),
        ]

        for log_type, log_path in log_files:
            # Tạo thread daemon: tự động tắt khi chương trình chính kết thúc
            thread = threading.Thread(
                target=self._tail_file,
                args=(log_type, log_path),
                name=f"monitor-{log_type}",
                daemon=True,  # Thread daemon tự tắt khi main thread kết thúc
            )
            thread.start()
            self._threads.append(thread)
            console.print(
                f"  [green]✓[/green] Đang giám sát: [cyan]{log_path}[/cyan] "
                f"(thread: {thread.name})"
            )

    def stop(self):
        """
        Dừng tất cả thread giám sát một cách an toàn (graceful shutdown).

        Set cờ _stop_event để tất cả thread thoát vòng lặp,
        sau đó đợi mỗi thread kết thúc (join) trong tối đa 2 giây.
        """
        console.print("[yellow]⏹ Đang dừng giám sát log...[/yellow]")
        self._stop_event.set()  # Bật cờ tín hiệu dừng
        for thread in self._threads:
            thread.join(timeout=2)  # Đợi thread kết thúc tối đa 2s

    def _tail_file(self, log_type: str, file_path: str):
        """
        Đọc liên tục dòng mới từ file log (tương tự lệnh `tail -f`).

        Thuật toán:
        1. Mở file, seek đến cuối (bỏ qua log cũ, chỉ xử lý log mới).
        2. Vòng lặp vô hạn:
           a. Đọc một dòng từ file.
           b. Nếu có dòng mới → strip() và đẩy vào queue.
           c. Nếu không có dòng mới → sleep một khoảng ngắn (POLL_INTERVAL).
        3. Xử lý file rotation: nếu vị trí đọc > kích thước file hiện tại,
           nghĩa là file đã bị truncate → seek về đầu file.

        Args:
            log_type: Loại log ("auth" hoặc "nginx"), dùng để tag dòng log.
            file_path: Đường dẫn tuyệt đối đến file log.
        """
        # Kiểm tra file có tồn tại không trước khi bắt đầu
        if not os.path.exists(file_path):
            console.print(
                f"  [red]✗ File không tồn tại:[/red] [dim]{file_path}[/dim]\n"
                f"    [dim]→ Thread {log_type} sẽ chờ file được tạo...[/dim]"
            )
            # Chờ file xuất hiện (ví dụ: Nginx chưa tạo log)
            while not os.path.exists(file_path) and not self._stop_event.is_set():
                time.sleep(1)
            if self._stop_event.is_set():
                return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                # Nhảy đến cuối file: chỉ đọc log MỚI từ thời điểm bắt đầu
                f.seek(0, os.SEEK_END)
                console.print(
                    f"  [green]↳[/green] [dim]{log_type}[/dim]: Đã seek đến cuối "
                    f"file, bắt đầu theo dõi log mới..."
                )

                # Lưu inode ban đầu để detect file rotation (logrotate thay file mới)
                try:
                    current_inode = os.stat(file_path).st_ino
                except OSError:
                    current_inode = None

                while not self._stop_event.is_set():
                    line = f.readline()

                    if line:
                        # Có dòng log mới → đóng gói và đẩy vào queue
                        stripped = line.strip()
                        if stripped:  # Bỏ qua dòng trống
                            try:
                                self.log_queue.put_nowait((log_type, stripped))
                            except Full:
                                # Queue đầy — bỏ dòng log này để không block monitor
                                pass
                    else:
                        # Không có dòng mới → kiểm tra file rotation
                        try:
                            current_pos = f.tell()
                            file_size = os.path.getsize(file_path)

                            if current_pos > file_size:
                                # File đã bị truncate (logrotate) → quay về đầu
                                console.print(
                                    f"  [yellow]↻[/yellow] [dim]{log_type}[/dim]: "
                                    f"File truncated, resetting position..."
                                )
                                f.seek(0)

                            # Kiểm tra inode: nếu file đã bị thay thế (logrotate
                            # move + create new), cần mở lại file mới
                            new_inode = os.stat(file_path).st_ino
                            if current_inode is not None and new_inode != current_inode:
                                console.print(
                                    f"  [yellow]↻[/yellow] [dim]{log_type}[/dim]: "
                                    f"File replaced (inode changed), reopening..."
                                )
                                break  # Thoát khỏi with block để mở lại file

                        except OSError:
                            # File bị xóa/thay thế → thoát và để vòng ngoài mở lại
                            break

                        # Nghỉ ngắn để tránh busy-waiting (tiết kiệm CPU)
                        time.sleep(POLL_INTERVAL)

            # Nếu thoát do file rotation, đệ quy gọi lại để mở file mới
            if not self._stop_event.is_set():
                self._tail_file(log_type, file_path)

        except PermissionError:
            console.print(
                f"  [bold red]✗ PERMISSION DENIED:[/bold red] Không thể đọc "
                f"[cyan]{file_path}[/cyan]\n"
                f"    [dim]→ Hãy chạy lại với sudo: [white]sudo python3 defender.py[/white][/dim]"
            )
        except Exception as e:
            console.print(
                f"  [bold red]✗ LỖI khi đọc {file_path}:[/bold red] {e}"
            )
