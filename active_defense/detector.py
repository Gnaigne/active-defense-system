# ============================================================================
# detector.py - Engine phát hiện tấn công (Attack Detection Engine)
# ============================================================================
# Module trung tâm của hệ thống. Nhận dòng log từ Queue, phân tích bằng
# regex, theo dõi tần suất, và kích hoạt hành động khi phát hiện tấn công.
#
# 4 kịch bản tấn công được hỗ trợ:
#   1. SSH Brute-Force      → auth.log
#   2. Directory Traversal  → nginx access.log
#   3. SQL Injection         → nginx access.log
#   4. HTTP DoS/Flood       → nginx access.log
# ============================================================================

import time
import threading
from queue import Queue, Empty
from collections import defaultdict, deque
from urllib.parse import unquote
from rich.console import Console
from rich.table import Table

from active_defense.config import (
    SSH_FAILED_PATTERN, NGINX_LOG_PATTERN,
    TRAVERSAL_PATTERNS, SQLI_PATTERNS,
    SSH_BRUTE_FORCE_THRESHOLD, SSH_BRUTE_FORCE_WINDOW,
    HTTP_FLOOD_THRESHOLD, HTTP_FLOOD_WINDOW,
    WHITELISTED_IPS,
    ATTACK_SSH_BRUTEFORCE, ATTACK_DIR_TRAVERSAL,
    ATTACK_SQLI, ATTACK_HTTP_FLOOD,
)

console = Console()


class AttackDetector:
    """
    Engine phát hiện tấn công dựa trên phân tích log.

    Nguyên lý hoạt động:
    - Consumer trong mô hình Producer-Consumer: lấy dòng log từ Queue
      (do LogMonitor đẩy vào) và phân tích.
    - Duy trì bộ đếm theo IP với cửa sổ thời gian trượt (sliding window)
      để phát hiện brute-force và flood.
    - Khi phát hiện tấn công → gọi callback để Firewall chặn IP và
      Alerter gửi cảnh báo.

    Data structures:
        _ssh_attempts:   dict[ip] → list[timestamp]   (SSH failed login)
        _http_requests:  dict[ip] → list[timestamp]   (HTTP request count)
        _blocked_ips:    set[ip]  (IP đã bị block, tránh block lặp lại)

    Attributes:
        log_queue: Queue nhận dòng log từ LogMonitor.
        on_attack: Callback function(ip, attack_type, log_line) được gọi
                   khi phát hiện tấn công.
    """

    def __init__(self, log_queue: Queue, on_attack_callback=None):
        """
        Khởi tạo AttackDetector.

        Args:
            log_queue: Queue chứa dòng log từ LogMonitor.
            on_attack_callback: Hàm callback được gọi khi phát hiện tấn công.
                                Signature: callback(ip: str, attack_type: str,
                                                     log_line: str)
        """
        self.log_queue = log_queue
        self.on_attack = on_attack_callback

        # --- Lock bảo vệ shared state (thread safety) ---
        self._lock = threading.Lock()

        # --- Bộ đếm SSH failed login theo IP ---
        # Key: IP address, Value: deque các timestamp login thất bại
        # deque hiệu quả hơn list cho sliding window (append/popleft O(1))
        self._ssh_attempts: dict[str, deque] = defaultdict(deque)

        # --- Bộ đếm HTTP request theo IP ---
        # Tương tự ssh_attempts nhưng cho HTTP request
        self._http_requests: dict[str, deque] = defaultdict(deque)

        # --- Tập hợp IP đã bị block ---
        # Dùng set để lookup O(1) và tránh gửi lệnh iptables trùng lặp
        self._blocked_ips: set[str] = set()

        # --- Thread control ---
        self._stop_event = threading.Event()
        self._thread = None

        # --- Thống kê ---
        self.stats = {
            "lines_processed": 0,
            "attacks_detected": 0,
            "ips_blocked": 0,
        }

        # --- Thời điểm cleanup cuối cùng ---
        self._last_cleanup = time.monotonic()
        self._CLEANUP_INTERVAL = 300  # Dọn dẹp IP cũ mỗi 5 phút

    def start(self):
        """
        Bắt đầu chạy detection engine trong thread riêng.

        Thread liên tục lấy dòng log từ queue và phân tích.
        """
        self._thread = threading.Thread(
            target=self._process_loop,
            name="detector-engine",
            daemon=True,
        )
        self._thread.start()
        console.print(
            "  [green]✓[/green] Detection engine đã khởi động "
            "(thread: detector-engine)"
        )

    def stop(self):
        """Dừng detection engine."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _process_loop(self):
        """
        Vòng lặp chính của detection engine.

        Liên tục lấy dòng log từ queue với timeout 0.5s.
        Timeout ngắn để thread có thể kiểm tra _stop_event thường xuyên
        và thoát nhanh khi được yêu cầu dừng.
        """
        while not self._stop_event.is_set():
            try:
                # Lấy dòng log từ queue, timeout 0.5s
                # Nếu queue rỗng quá 0.5s → ném Empty exception → tiếp tục loop
                log_type, line = self.log_queue.get(timeout=0.5)
                with self._lock:
                    self.stats["lines_processed"] += 1

                # Phân loại và xử lý dòng log theo loại
                if log_type == "auth":
                    self._analyze_auth_log(line)
                elif log_type == "nginx":
                    self._analyze_nginx_log(line)

                # Dọn dẹp định kỳ IP cũ để tránh memory leak
                self._periodic_cleanup()

            except Empty:
                # Queue rỗng, không có log mới → quay lại kiểm tra stop_event
                continue

    # ======================== PHÂN TÍCH AUTH.LOG ============================

    def _analyze_auth_log(self, line: str):
        """
        Phân tích dòng log từ auth.log để phát hiện SSH Brute-Force.

        Thuật toán Sliding Window:
        1. Dùng regex bắt dòng "Failed password" và trích xuất IP.
        2. Ghi nhận timestamp của lần login thất bại.
        3. Loại bỏ các timestamp cũ hơn SSH_BRUTE_FORCE_WINDOW giây
           (cửa sổ thời gian trượt).
        4. Nếu số lần thất bại còn lại >= ngưỡng → BRUTE-FORCE DETECTED!

        Args:
            line: Một dòng log từ auth.log.
        """
        match = SSH_FAILED_PATTERN.search(line)
        if not match:
            return  # Dòng log không phải "Failed password" → bỏ qua

        ip = match.group("ip")

        # Kiểm tra whitelist: không xử lý IP được miễn trừ
        if ip in WHITELISTED_IPS:
            return

        # Kiểm tra đã block chưa: tránh xử lý lặp
        if ip in self._blocked_ips:
            return

        now = time.time()

        # Thêm timestamp hiện tại vào deque attempts của IP
        self._ssh_attempts[ip].append(now)

        # Sliding Window: loại bỏ timestamp cũ từ đầu deque (O(1) mỗi lần pop)
        cutoff = now - SSH_BRUTE_FORCE_WINDOW
        attempts = self._ssh_attempts[ip]
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

        # Đếm số lần thất bại trong cửa sổ
        attempt_count = len(attempts)

        # Log từng lần thất bại để debug
        console.print(
            f"  [yellow]⚠[/yellow] SSH Failed Login: [red]{ip}[/red] "
            f"({attempt_count}/{SSH_BRUTE_FORCE_THRESHOLD} trong "
            f"{SSH_BRUTE_FORCE_WINDOW}s)"
        )

        # Kiểm tra ngưỡng: nếu vượt → kích hoạt phòng vệ
        if attempt_count >= SSH_BRUTE_FORCE_THRESHOLD:
            self._trigger_attack(ip, ATTACK_SSH_BRUTEFORCE, line)
            # Reset bộ đếm cho IP này sau khi đã block
            self._ssh_attempts[ip].clear()

    # ======================== PHÂN TÍCH NGINX LOG ===========================

    def _analyze_nginx_log(self, line: str):
        """
        Phân tích dòng log từ nginx access.log.

        Thực hiện 3 kiểm tra tuần tự trên mỗi dòng log:
        1. Directory/File Traversal: kiểm tra path chứa file nhạy cảm.
        2. SQL Injection: kiểm tra path/query chứa SQL keyword.
        3. HTTP Flood: đếm tần suất request từ cùng IP.

        Nếu bất kỳ kiểm tra nào match → kích hoạt tấn công tương ứng.

        Args:
            line: Một dòng log từ nginx access.log.
        """
        match = NGINX_LOG_PATTERN.search(line)
        if not match:
            return  # Dòng log không đúng format → bỏ qua

        ip = match.group("ip")
        path = match.group("path")

        # Bỏ qua IP trong whitelist hoặc đã bị block
        if ip in WHITELISTED_IPS or ip in self._blocked_ips:
            return

        # --- Kiểm tra 1: Directory/File Traversal ---
        if TRAVERSAL_PATTERNS.search(path):
            console.print(
                f"  [yellow]⚠[/yellow] Traversal Detected: [red]{ip}[/red] "
                f"→ [cyan]{path}[/cyan]"
            )
            self._trigger_attack(ip, ATTACK_DIR_TRAVERSAL, line)
            return  # Đã phát hiện tấn công, không cần kiểm tra thêm

        # --- Kiểm tra 2: SQL Injection ---
        # Decode URL path trước khi check (attacker thường encode payload)
        decoded_path = unquote(path)

        if SQLI_PATTERNS.search(decoded_path):
            console.print(
                f"  [yellow]⚠[/yellow] SQLi Detected: [red]{ip}[/red] "
                f"→ [cyan]{decoded_path}[/cyan]"
            )
            self._trigger_attack(ip, ATTACK_SQLI, line)
            return

        # --- Kiểm tra 3: HTTP DoS/Flood (Sliding Window) ---
        self._check_http_flood(ip, line)

    def _check_http_flood(self, ip: str, line: str):
        """
        Kiểm tra HTTP DoS/Flood bằng Sliding Window.

        Tương tự SSH Brute-Force nhưng đếm số request HTTP thay vì
        số lần login thất bại.

        Args:
            ip: Địa chỉ IP của client.
            line: Dòng log gốc (để trích dẫn trong cảnh báo).
        """
        now = time.time()
        self._http_requests[ip].append(now)

        # Sliding Window: loại bỏ timestamp cũ từ đầu deque (O(1) mỗi lần pop)
        cutoff = now - HTTP_FLOOD_WINDOW
        requests_dq = self._http_requests[ip]
        while requests_dq and requests_dq[0] <= cutoff:
            requests_dq.popleft()

        request_count = len(requests_dq)

        # Chỉ cảnh báo khi vượt ngưỡng
        if request_count >= HTTP_FLOOD_THRESHOLD:
            console.print(
                f"  [yellow]⚠[/yellow] HTTP Flood: [red]{ip}[/red] "
                f"({request_count} requests trong {HTTP_FLOOD_WINDOW}s)"
            )
            self._trigger_attack(ip, ATTACK_HTTP_FLOOD, line)
            # Reset bộ đếm sau khi block
            self._http_requests[ip].clear()

    # ======================== KÍCH HOẠT HÀNH ĐỘNG ===========================

    def _trigger_attack(self, ip: str, attack_type: str, log_line: str):
        """
        Kích hoạt quy trình phòng vệ khi phát hiện tấn công.

        1. Đánh dấu IP vào tập blocked (tránh xử lý lặp).
        2. Cập nhật thống kê.
        3. In cảnh báo ra console.
        4. Gọi callback để Firewall + Alerter xử lý.

        Args:
            ip: IP vi phạm.
            attack_type: Loại tấn công (dùng hằng số từ config).
            log_line: Dòng log gốc gây ra cảnh báo.
        """
        # Cập nhật thống kê (thread-safe)
        with self._lock:
            self._blocked_ips.add(ip)
            self.stats["attacks_detected"] += 1
            self.stats["ips_blocked"] += 1

        # In cảnh báo nổi bật ra console
        console.print()
        console.print(
            f"  [bold red]🚨 TẤN CÔNG PHÁT HIỆN![/bold red]",
            highlight=False,
        )
        console.print(f"     Loại  : [bold yellow]{attack_type}[/bold yellow]")
        console.print(f"     IP    : [bold red]{ip}[/bold red]")
        console.print(f"     Log   : [dim]{log_line[:120]}[/dim]")
        console.print()

        # Gọi callback (Firewall block + Discord alert)
        # Bọc trong try-except để tránh crash detector thread
        if self.on_attack:
            try:
                self.on_attack(ip, attack_type, log_line)
            except Exception as e:
                console.print(
                    f"  [bold red]✗ Lỗi trong callback phòng vệ:[/bold red] {e}"
                )

    def get_stats(self) -> dict:
        """Trả về bản copy thread-safe của thống kê."""
        with self._lock:
            return self.stats.copy()

    def print_stats(self):
        """
        In bảng thống kê hoạt động của detection engine.
        Dùng rich Table để hiển thị đẹp trên console.
        """
        stats = self.get_stats()
        table = Table(title="📊 Thống kê Detection Engine")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        table.add_row("Dòng log đã xử lý", str(stats["lines_processed"]))
        table.add_row("Tấn công phát hiện", str(stats["attacks_detected"]))
        table.add_row("IP đã block", str(stats["ips_blocked"]))
        table.add_row("IP đang theo dõi (SSH)", str(len(self._ssh_attempts)))
        table.add_row("IP đang theo dõi (HTTP)", str(len(self._http_requests)))
        console.print(table)

    def _periodic_cleanup(self):
        """
        Dọn dẹp định kỳ các entry cũ trong sliding window dict.
        Tránh memory leak khi có nhiều IP unique qua thời gian dài.
        """
        now = time.monotonic()
        if now - self._last_cleanup < self._CLEANUP_INTERVAL:
            return
        self._last_cleanup = now

        # Xóa IP đã bị block hoặc không còn attempt nào trong window
        current_time = time.time()

        ssh_cutoff = current_time - SSH_BRUTE_FORCE_WINDOW
        stale_ssh = [
            ip for ip, dq in self._ssh_attempts.items()
            if not dq or dq[-1] <= ssh_cutoff
        ]
        for ip in stale_ssh:
            del self._ssh_attempts[ip]

        http_cutoff = current_time - HTTP_FLOOD_WINDOW
        stale_http = [
            ip for ip, dq in self._http_requests.items()
            if not dq or dq[-1] <= http_cutoff
        ]
        for ip in stale_http:
            del self._http_requests[ip]
