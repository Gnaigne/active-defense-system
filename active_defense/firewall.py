# ============================================================================
# firewall.py - Module quản lý tường lửa (iptables)
# ============================================================================
# Chịu trách nhiệm thực thi lệnh iptables để chặn IP tấn công.
# Sử dụng subprocess để gọi lệnh hệ thống một cách an toàn.
#
# Lưu ý bảo mật:
# - Luôn validate IP trước khi đưa vào lệnh iptables (tránh injection).
# - Kiểm tra whitelist trước khi block.
# - Chỉ hoạt động khi chạy với quyền root/sudo.
# ============================================================================

import re
import subprocess
import threading
from ipaddress import IPv4Address, AddressValueError
from rich.console import Console

from active_defense.config import WHITELISTED_IPS

console = Console()

# Regex validate IPv4: chỉ cho phép địa chỉ IP hợp lệ
# Phòng chống command injection: nếu IP chứa ký tự lạ → từ chối
IP_VALIDATE_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


class Firewall:
    """
    Quản lý tường lửa Linux (iptables) để chặn IP tấn công.

    Nguyên lý:
    - Thêm rule DROP vào chain INPUT của iptables.
    - Mỗi IP chỉ được block 1 lần (kiểm tra trùng lặp).
    - Hỗ trợ unblock IP và liệt kê tất cả rule đã thêm.

    Yêu cầu: chương trình phải chạy với quyền root (sudo).

    Attributes:
        _blocked_ips (set): Tập hợp IP đã bị block bởi module này.
        dry_run (bool): Nếu True, chỉ in lệnh mà không thực thi
                        (dùng để test mà không cần sudo).
    """

    def __init__(self, dry_run: bool = False):
        """
        Khởi tạo Firewall.

        Args:
            dry_run: Nếu True, chỉ mô phỏng (không thực sự gọi iptables).
                     Hữu ích khi test trên máy không có quyền root.
        """
        self._blocked_ips: set[str] = set()
        self._lock = threading.Lock()
        self.dry_run = dry_run

        if dry_run:
            console.print(
                "  [yellow]⚠ Firewall chạy ở chế độ DRY-RUN[/yellow] "
                "(không thực thi iptables)"
            )

    def block_ip(self, ip: str) -> bool:
        """
        Chặn một IP bằng iptables.

        Quy trình:
        1. Validate IP (format đúng, không chứa ký tự nguy hiểm).
        2. Kiểm tra whitelist.
        3. Kiểm tra đã block chưa (tránh rule trùng lặp).
        4. Thực thi lệnh: iptables -A INPUT -s <IP> -j DROP

        Args:
            ip: Địa chỉ IPv4 cần chặn.

        Returns:
            True nếu block thành công, False nếu thất bại hoặc bị bỏ qua.
        """
        # === Bước 1: Validate IP ===
        # Phòng chống command injection và validate octet 0-255
        try:
            IPv4Address(ip)
        except (AddressValueError, ValueError):
            console.print(
                f"  [red]✗ IP không hợp lệ:[/red] '{ip}' — bỏ qua để tránh "
                f"command injection."
            )
            return False

        # === Bước 2: Kiểm tra whitelist ===
        if ip in WHITELISTED_IPS:
            console.print(
                f"  [yellow]⊘ IP {ip} nằm trong whitelist[/yellow] — không block."
            )
            return False

        # === Bước 3: Kiểm tra trùng lặp ===
        with self._lock:
            if ip in self._blocked_ips:
                console.print(
                    f"  [dim]↳ IP {ip} đã được block trước đó — bỏ qua.[/dim]"
                )
                return False

        # === Bước 4: Thực thi iptables ===
        command = ["iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"]

        if self.dry_run:
            # Chế độ DRY-RUN: chỉ in lệnh mà không thực thi
            console.print(
                f"  [blue]🔒 DRY-RUN:[/blue] {' '.join(command)}"
            )
            with self._lock:
                self._blocked_ips.add(ip)
            return True

        try:
            # Gọi iptables qua subprocess
            # - check=True: ném CalledProcessError nếu return code != 0
            # - capture_output=True: bắt stdout/stderr để log
            # - timeout=10: tránh treo nếu iptables bị lock
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            with self._lock:
                self._blocked_ips.add(ip)
            console.print(
                f"  [bold green]🔒 ĐÃ BLOCK:[/bold green] {ip} "
                f"(iptables -A INPUT -s {ip} -j DROP)"
            )
            return True

        except subprocess.CalledProcessError as e:
            # Lệnh iptables thất bại (ví dụ: không có quyền root)
            console.print(
                f"  [bold red]✗ BLOCK THẤT BẠI:[/bold red] {ip}\n"
                f"    stderr: {e.stderr.strip() if e.stderr else 'N/A'}\n"
                f"    [dim]→ Hãy chạy lại với sudo.[/dim]"
            )
            return False

        except subprocess.TimeoutExpired:
            console.print(
                f"  [bold red]✗ TIMEOUT:[/bold red] Lệnh iptables bị treo "
                f"khi block {ip}"
            )
            return False

        except FileNotFoundError:
            console.print(
                f"  [bold red]✗ KHÔNG TÌM THẤY iptables![/bold red]\n"
                f"    [dim]→ Hãy cài đặt: sudo apt install iptables[/dim]"
            )
            return False

        except Exception as e:
            console.print(
                f"  [bold red]✗ LỖI KHÔNG XÁC ĐỊNH khi block {ip}:[/bold red] {e}"
            )
            return False

    def unblock_ip(self, ip: str) -> bool:
        """
        Gỡ block một IP (xóa rule DROP khỏi iptables).

        Dùng lệnh: iptables -D INPUT -s <IP> -j DROP

        Args:
            ip: Địa chỉ IPv4 cần unblock.

        Returns:
            True nếu unblock thành công, False nếu thất bại.
        """
        if not IP_VALIDATE_PATTERN.match(ip):
            console.print(f"  [red]✗ IP không hợp lệ:[/red] '{ip}'")
            return False

        command = ["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"]

        if self.dry_run:
            console.print(f"  [blue]🔓 DRY-RUN:[/blue] {' '.join(command)}")
            with self._lock:
                self._blocked_ips.discard(ip)
            return True

        try:
            subprocess.run(
                command, check=True, capture_output=True, text=True, timeout=10
            )
            with self._lock:
                self._blocked_ips.discard(ip)
            console.print(f"  [green]🔓 ĐÃ UNBLOCK:[/green] {ip}")
            return True

        except subprocess.CalledProcessError as e:
            console.print(
                f"  [red]✗ UNBLOCK THẤT BẠI:[/red] {ip} — "
                f"{e.stderr.strip() if e.stderr else 'Rule không tồn tại'}"
            )
            return False

        except Exception as e:
            console.print(f"  [red]✗ LỖI khi unblock {ip}:[/red] {e}")
            return False

    def get_blocked_ips(self) -> set:
        """Trả về tập hợp IP đã bị block (thread-safe copy)."""
        with self._lock:
            return self._blocked_ips.copy()

    def get_blocked_count(self) -> int:
        """Trả về số lượng IP đã bị block (thread-safe)."""
        with self._lock:
            return len(self._blocked_ips)
