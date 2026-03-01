#!/usr/bin/env python3
# ============================================================================
#
#    ██████╗ ███████╗███████╗███████╗███╗   ██╗██████╗ ███████╗██████╗
#    ██╔══██╗██╔════╝██╔════╝██╔════╝████╗  ██║██╔══██╗██╔════╝██╔══██╗
#    ██║  ██║█████╗  █████╗  █████╗  ██╔██╗ ██║██║  ██║█████╗  ██████╔╝
#    ██║  ██║██╔══╝  ██╔══╝  ██╔══╝  ██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗
#    ██████╔╝███████╗██║     ███████╗██║ ╚████║██████╔╝███████╗██║  ██║
#    ╚═════╝ ╚══════╝╚═╝     ╚══════╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝
#
#    Automated Active Defense & Alert System v1.0
#    Mini IPS (Intrusion Prevention System) cho máy chủ Linux
#
# ============================================================================
# defender.py - Entry Point chính của hệ thống
# ============================================================================
# File này là điểm khởi chạy duy nhất. Nó khởi tạo và kết nối tất cả
# các component (Monitor, Detector, Firewall, Alerter) lại với nhau,
# sau đó chạy vòng lặp chính cho đến khi người dùng nhấn Ctrl+C.
#
# Cách chạy:
#   sudo python3 defender.py                  # Chế độ thật (cần root)
#   python3 defender.py --dry-run             # Chế độ test (không cần root)
#   python3 defender.py --dry-run --verbose   # Test + log chi tiết
# ============================================================================

import os
import sys
import signal
import argparse
import time
from queue import Queue

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from rich import box

# Import các module của hệ thống
from active_defense.monitor import LogMonitor
from active_defense.detector import AttackDetector
from active_defense.firewall import Firewall
from active_defense.alerter import DiscordAlerter
from active_defense.config import (
    AUTH_LOG, NGINX_LOG, DISCORD_WEBHOOK_URL,
    SSH_BRUTE_FORCE_THRESHOLD, SSH_BRUTE_FORCE_WINDOW,
    HTTP_FLOOD_THRESHOLD, HTTP_FLOOD_WINDOW,
    WHITELISTED_IPS,
)

console = Console()


# ============================================================================
# BANNER & DISPLAY
# ============================================================================

BANNER = """
[bold cyan]
    ██████╗ ███████╗███████╗███████╗███╗   ██╗██████╗ ███████╗██████╗
    ██╔══██╗██╔════╝██╔════╝██╔════╝████╗  ██║██╔══██╗██╔════╝██╔══██╗
    ██║  ██║█████╗  █████╗  █████╗  ██╔██╗ ██║██║  ██║█████╗  ██████╔╝
    ██║  ██║██╔══╝  ██╔══╝  ██╔══╝  ██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗
    ██████╔╝███████╗██║     ███████╗██║ ╚████║██████╔╝███████╗██║  ██║
    ╚═════╝ ╚══════╝╚═╝     ╚══════╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝
[/bold cyan]
[bold white]    Automated Active Defense & Alert System v1.0[/bold white]
[dim]    Mini IPS for Linux Servers — Monitor · Detect · Act · Alert[/dim]
"""


def print_config_table(dry_run: bool):
    """
    In bảng cấu hình hiện tại ra console để người dùng verify.

    Bảng hiển thị:
    - Đường dẫn file log đang giám sát
    - Ngưỡng phát hiện tấn công
    - Trạng thái Discord Webhook
    - Chế độ hoạt động (Real/Dry-run)

    Args:
        dry_run: True nếu đang ở chế độ dry-run.
    """
    table = Table(
        title="⚙️  Cấu hình hệ thống",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Tham số", style="cyan", width=30)
    table.add_column("Giá trị", style="white")

    # --- Log files ---
    auth_status = "✅ Exists" if os.path.exists(AUTH_LOG) else "❌ Not found"
    nginx_status = "✅ Exists" if os.path.exists(NGINX_LOG) else "❌ Not found"
    table.add_row("Auth Log", f"{AUTH_LOG}  ({auth_status})")
    table.add_row("Nginx Log", f"{NGINX_LOG}  ({nginx_status})")

    # --- Thresholds ---
    table.add_row(
        "SSH Brute-Force",
        f"{SSH_BRUTE_FORCE_THRESHOLD} attempts / {SSH_BRUTE_FORCE_WINDOW}s"
    )
    table.add_row(
        "HTTP Flood",
        f"{HTTP_FLOOD_THRESHOLD} requests / {HTTP_FLOOD_WINDOW}s"
    )

    # --- Discord ---
    discord_status = "✅ Configured" if DISCORD_WEBHOOK_URL else "⚠️  Not set"
    table.add_row("Discord Webhook", discord_status)

    # --- Whitelist ---
    table.add_row("Whitelisted IPs", ", ".join(WHITELISTED_IPS) or "None")

    # --- Mode ---
    mode = "[yellow]🧪 DRY-RUN (test)[/yellow]" if dry_run else "[green]🔒 REAL MODE[/green]"
    table.add_row("Chế độ", mode)

    # --- Root check ---
    is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
    root_status = "[green]✅ Root[/green]" if is_root else "[yellow]⚠️  Non-root[/yellow]"
    table.add_row("Quyền hệ thống", root_status)

    console.print(table)
    console.print()


# ============================================================================
# MAIN DEFENDER CLASS
# ============================================================================

class ActiveDefender:
    """
    Lớp điều phối chính (Orchestrator) của hệ thống Active Defense.

    Chịu trách nhiệm:
    1. Khởi tạo tất cả component: Monitor, Detector, Firewall, Alerter.
    2. Kết nối chúng lại qua Queue (Monitor→Detector) và callback
       (Detector→Firewall+Alerter).
    3. Quản lý lifecycle: start, run loop, graceful shutdown.

    Kiến trúc:
        LogMonitor ──(Queue)──> AttackDetector ──(callback)──> Firewall
                                                           └──> DiscordAlerter

    Attributes:
        dry_run (bool): Chế độ test.
        log_queue (Queue): Hàng đợi trung chuyển dòng log.
        monitor (LogMonitor): Instance giám sát log.
        detector (AttackDetector): Instance phát hiện tấn công.
        firewall (Firewall): Instance quản lý iptables.
        alerter (DiscordAlerter): Instance gửi cảnh báo Discord.
    """

    def __init__(self, dry_run: bool = False):
        """
        Khởi tạo ActiveDefender và tất cả component.

        Args:
            dry_run: Nếu True, không thực sự gọi iptables.
        """
        self.dry_run = dry_run
        self._shutdown = False  # Cờ tránh shutdown 2 lần

        # Queue dùng làm kênh giao tiếp giữa Monitor và Detector
        # maxsize=10000 để tránh memory leak nếu Detector xử lý chậm
        self.log_queue = Queue(maxsize=10000)

        # Khởi tạo các component
        console.print("\n[bold]🔧 Khởi tạo các module...[/bold]")

        # 1. Firewall — chặn IP qua iptables
        self.firewall = Firewall(dry_run=dry_run)

        # 2. Alerter — gửi cảnh báo Discord
        self.alerter = DiscordAlerter()

        # 3. Detector — phát hiện tấn công, gắn callback
        self.detector = AttackDetector(
            log_queue=self.log_queue,
            on_attack_callback=self._on_attack_detected,
        )

        # 4. Monitor — giám sát file log, đẩy vào queue
        self.monitor = LogMonitor(log_queue=self.log_queue)

        console.print("[bold green]✅ Tất cả module đã sẵn sàng![/bold green]\n")

    def _on_attack_detected(self, ip: str, attack_type: str, log_line: str):
        """
        Callback được gọi bởi Detector khi phát hiện tấn công.

        Thực hiện 2 hành động:
        1. Block IP qua Firewall (iptables).
        2. Gửi cảnh báo qua Discord Webhook.

        Args:
            ip: IP tấn công.
            attack_type: Loại tấn công.
            log_line: Dòng log gốc.
        """
        # Bước 1: Chặn IP
        blocked = self.firewall.block_ip(ip)

        # Bước 2: Gửi cảnh báo Discord (kèm trạng thái block)
        self.alerter.send_alert(
            ip=ip,
            attack_type=attack_type,
            log_line=log_line,
            blocked=blocked,
        )

    def start(self):
        """
        Khởi chạy toàn bộ hệ thống.

        Bật Monitor (bắt đầu đọc log) và Detector (bắt đầu phân tích).
        """
        console.print("[bold]🚀 Khởi chạy hệ thống giám sát...[/bold]\n")
        self.monitor.start()
        self.detector.start()
        console.print(
            Panel(
                "[bold green]HỆ THỐNG ĐANG HOẠT ĐỘNG[/bold green]\n"
                "[dim]Đang giám sát log... Nhấn Ctrl+C để dừng.[/dim]",
                border_style="green",
                padding=(1, 2),
            )
        )

    def stop(self):
        """
        Dừng toàn bộ hệ thống một cách an toàn (graceful shutdown).

        Dừng Monitor trước (ngừng đọc log), sau đó dừng Detector.
        In thống kê trước khi thoát.
        """
        if self._shutdown:
            return  # Tránh shutdown lặp
        self._shutdown = True

        console.print("\n[bold yellow]⏹ Đang tắt hệ thống...[/bold yellow]")
        self.monitor.stop()
        self.detector.stop()

        # In thống kê phiên làm việc
        self.detector.print_stats()
        blocked_count = self.firewall.get_blocked_count()
        if blocked_count > 0:
            blocked_ips = self.firewall.get_blocked_ips()
            console.print(
                f"\n[bold]📋 Danh sách IP đã block ({blocked_count}):[/bold]"
            )
            for ip in sorted(blocked_ips):
                console.print(f"   • [red]{ip}[/red]")

        console.print(
            "\n[bold green]👋 Hệ thống đã tắt an toàn. Goodbye![/bold green]\n"
        )

    def run_forever(self):
        """
        Vòng lặp chính — giữ chương trình chạy cho đến khi Ctrl+C.

        Mỗi 30 giây in một dòng heartbeat để biết hệ thống còn sống.
        """
        try:
            iteration = 0
            while True:
                time.sleep(30)
                iteration += 1
                stats = self.detector.get_stats()
                lines = stats["lines_processed"]
                attacks = stats["attacks_detected"]
                blocked = self.firewall.get_blocked_count()
                console.print(
                    f"  [dim]💓 Heartbeat #{iteration}: "
                    f"{lines} lines | {attacks} attacks | "
                    f"{blocked} blocked IPs | Queue: {self.log_queue.qsize()}[/dim]"
                )
        except KeyboardInterrupt:
            pass


# ============================================================================
# CLI ARGUMENT PARSING
# ============================================================================

def parse_arguments():
    """
    Phân tích tham số dòng lệnh (CLI arguments).

    Returns:
        argparse.Namespace chứa các tham số đã parse.
    """
    parser = argparse.ArgumentParser(
        description="🛡️ Active Defense System — Mini IPS for Linux Servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ sử dụng:
  sudo python3 defender.py                     # Chạy thật (cần root cho iptables)
  python3 defender.py --dry-run                # Chạy thử (không cần root)
  python3 defender.py --dry-run --verbose      # Chạy thử + log chi tiết

Biến môi trường (hoặc file .env):
  DISCORD_WEBHOOK_URL    URL Discord Webhook
  AUTH_LOG_PATH          Đường dẫn auth.log (mặc định: /var/log/auth.log)
  NGINX_LOG_PATH         Đường dẫn nginx access.log
  SSH_BRUTE_FORCE_THRESHOLD  Ngưỡng brute-force (mặc định: 5)
  HTTP_FLOOD_THRESHOLD       Ngưỡng flood (mặc định: 100)
  WHITELISTED_IPS            Danh sách IP whitelist, cách nhau bởi dấu phẩy
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chế độ test: chỉ in lệnh iptables mà không thực thi. "
             "Không cần quyền root.",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Hiển thị log chi tiết hơn (debug mode).",
    )

    return parser.parse_args()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """
    Hàm main — điểm bắt đầu thực thi chương trình.

    Luồng thực thi:
    1. Parse CLI arguments.
    2. In banner và bảng cấu hình.
    3. Cảnh báo nếu không chạy với quyền root (ở chế độ thật).
    4. Khởi tạo ActiveDefender.
    5. Đăng ký signal handler cho SIGTERM (graceful shutdown).
    6. Start hệ thống và chạy vòng lặp chính.
    7. Khi Ctrl+C → dừng hệ thống an toàn.
    """
    # === Bước 1: Parse arguments ===
    args = parse_arguments()

    # === Bước 2: In banner ===
    console.print(BANNER)
    print_config_table(args.dry_run)

    # === Bước 3: Kiểm tra quyền root ===
    is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
    if not args.dry_run and not is_root:
        console.print(
            Panel(
                "[bold yellow]⚠️  CẢNH BÁO: Không có quyền root![/bold yellow]\n\n"
                "Hệ thống cần quyền root để thực thi lệnh iptables.\n"
                "Chạy lại với: [bold]sudo python3 defender.py[/bold]\n\n"
                "Hoặc dùng chế độ test: [bold]python3 defender.py --dry-run[/bold]",
                border_style="yellow",
                padding=(1, 2),
            )
        )
        sys.exit(1)

    # === Bước 4: Khởi tạo hệ thống ===
    defender = ActiveDefender(dry_run=args.dry_run)

    # === Bước 5: Đăng ký signal handler ===
    # Khi nhận SIGTERM (từ systemctl stop hoặc kill), dừng an toàn
    def signal_handler(signum, frame):
        console.print(f"\n[yellow]📡 Nhận signal {signum}, đang dừng...[/yellow]")
        defender.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # === Bước 6: Start & Run ===
    defender.start()
    defender.run_forever()

    # === Bước 7: Cleanup (nếu thoát không qua signal) ===
    defender.stop()


if __name__ == "__main__":
    main()
