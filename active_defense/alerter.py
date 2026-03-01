# ============================================================================
# alerter.py - Module gửi cảnh báo qua Discord Webhook
# ============================================================================
# Khi phát hiện tấn công, module này gửi một embed message đến
# Discord channel qua Webhook URL đã cấu hình.
#
# Payload bao gồm: Thời gian, IP, Loại tấn công, Trích xuất log.
# Sử dụng Discord Embed format để hiển thị đẹp và dễ đọc.
# ============================================================================

import time
import datetime
import threading
import requests
from rich.console import Console

from active_defense.config import DISCORD_WEBHOOK_URL

console = Console()

# Mapping loại tấn công → màu embed Discord (dạng integer)
# Discord dùng decimal color, không phải hex
ATTACK_COLORS = {
    "SSH Brute-Force": 15158332,       # Đỏ (#E74C3C)
    "Directory/File Traversal": 15105570,  # Cam (#E67E22)
    "SQL Injection": 10038562,         # Tím đậm (#9B59B6)
    "HTTP DoS/Flood": 15844367,        # Vàng (#F1C40F)
}

# Mapping loại tấn công → emoji
ATTACK_EMOJIS = {
    "SSH Brute-Force": "🔐",
    "Directory/File Traversal": "📂",
    "SQL Injection": "💉",
    "HTTP DoS/Flood": "🌊",
}


class DiscordAlerter:
    """
    Gửi cảnh báo tấn công đến Discord qua Webhook.

    Sử dụng Discord Webhook API để gửi embed message với thông tin:
    - Thời gian phát hiện
    - IP tấn công
    - Loại tấn công
    - Trích xuất dòng log gốc
    - Hành động đã thực hiện (block/không block)

    Attributes:
        webhook_url (str): Discord Webhook URL.
        enabled (bool): True nếu webhook đã được cấu hình.
    """

    def __init__(self, webhook_url: str = None):
        """
        Khởi tạo DiscordAlerter.

        Args:
            webhook_url: Discord Webhook URL. Nếu None, lấy từ config.
        """
        self.webhook_url = webhook_url or DISCORD_WEBHOOK_URL
        self.enabled = bool(self.webhook_url)

        # Rate limiting: tối đa 4 request mỗi 2 giây (dưới ngưỡng Discord 5/2s)
        self._rate_lock = threading.Lock()
        self._send_timestamps: list[float] = []
        self._RATE_LIMIT = 4
        self._RATE_WINDOW = 2.0

        # Session để reuse connection (TCP keep-alive, giảm overhead)
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

        if not self.enabled:
            console.print(
                "  [yellow]⚠ Discord Webhook chưa được cấu hình.[/yellow]\n"
                "    [dim]→ Set biến DISCORD_WEBHOOK_URL trong .env để nhận "
                "cảnh báo.[/dim]"
            )
        else:
            # Hiển thị URL đã che (chỉ hiện 20 ký tự đầu) để bảo mật
            masked = self.webhook_url[:40] + "..."
            console.print(
                f"  [green]✓[/green] Discord Webhook: [dim]{masked}[/dim]"
            )

    def send_alert(
        self,
        ip: str,
        attack_type: str,
        log_line: str,
        blocked: bool = True
    ):
        """
        Gửi cảnh báo tấn công đến Discord.

        Tạo một embed message chứa đầy đủ thông tin về sự kiện tấn công
        và gửi qua HTTP POST đến Discord Webhook URL.

        Args:
            ip: IP tấn công.
            attack_type: Loại tấn công (ví dụ: "SSH Brute-Force").
            log_line: Dòng log gốc gây ra cảnh báo.
            blocked: True nếu IP đã bị block thành công.
        """
        if not self.enabled:
            return

        # Rate limiting: chờ nếu đã gửi quá nhiều request gần đây
        self._wait_for_rate_limit()

        # Lấy thời gian hiện tại theo ISO 8601
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        emoji = ATTACK_EMOJIS.get(attack_type, "🚨")
        color = ATTACK_COLORS.get(attack_type, 3447003)  # Default: xanh

        # Trích xuất log (giới hạn 500 ký tự để tránh vượt giới hạn Discord)
        log_excerpt = log_line[:500]

        # Trạng thái hành động
        action_status = "✅ IP đã bị BLOCK" if blocked else "⚠️ BLOCK THẤT BẠI"

        # === Tạo Discord Embed payload ===
        # Tham khảo: https://discord.com/developers/docs/resources/webhook
        payload = {
            "username": "🛡️ Active Defense",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2716/2716607.png",
            "embeds": [
                {
                    "title": f"{emoji} {attack_type} Detected!",
                    "color": color,
                    "fields": [
                        {
                            "name": "🌐 IP Address",
                            "value": f"`{ip}`",
                            "inline": True,
                        },
                        {
                            "name": "⚔️ Attack Type",
                            "value": attack_type,
                            "inline": True,
                        },
                        {
                            "name": "🔒 Action",
                            "value": action_status,
                            "inline": True,
                        },
                        {
                            "name": "📋 Log Excerpt",
                            "value": f"```\n{log_excerpt}\n```",
                            "inline": False,
                        },
                    ],
                    "timestamp": timestamp,
                    "footer": {
                        "text": "Active Defense System v1.0"
                    },
                }
            ],
        }

        # === Gửi HTTP POST đến Discord Webhook ===
        try:
            response = self._session.post(
                self.webhook_url,
                json=payload,
                timeout=10,  # Timeout 10s tránh block thread quá lâu
            )

            # Discord trả về 204 No Content khi thành công
            if response.status_code in (200, 204):
                console.print(
                    f"  [green]📨 Đã gửi cảnh báo Discord:[/green] "
                    f"{attack_type} — {ip}"
                )
            else:
                console.print(
                    f"  [red]✗ Discord webhook lỗi:[/red] "
                    f"HTTP {response.status_code} — {response.text[:200]}"
                )

        except requests.exceptions.ConnectionError:
            console.print(
                f"  [red]✗ Không thể kết nối Discord Webhook.[/red]\n"
                f"    [dim]→ Kiểm tra kết nối mạng và URL webhook.[/dim]"
            )

        except requests.exceptions.Timeout:
            console.print(
                f"  [red]✗ Discord Webhook timeout (>10s).[/red]"
            )

        except requests.exceptions.RequestException as e:
            console.print(
                f"  [red]✗ Lỗi gửi Discord webhook:[/red] {e}"
            )

    def _wait_for_rate_limit(self):
        """
        Đảm bảo không vượt rate limit của Discord Webhook.
        Nếu đã gửi >= _RATE_LIMIT request trong _RATE_WINDOW giây gần nhất,
        chờ cho đến khi window trối qua.
        """
        with self._rate_lock:
            now = time.monotonic()
            # Xóa timestamp cũ ngoài window
            self._send_timestamps = [
                t for t in self._send_timestamps
                if now - t < self._RATE_WINDOW
            ]
            if len(self._send_timestamps) >= self._RATE_LIMIT:
                # Cần chờ: tính thời gian còn lại của request cũ nhất
                sleep_time = self._RATE_WINDOW - (now - self._send_timestamps[0])
                if sleep_time > 0:
                    console.print(
                        f"  [dim]⏳ Rate limit: chờ {sleep_time:.1f}s...[/dim]"
                    )
                    time.sleep(sleep_time)
            self._send_timestamps.append(time.monotonic())
