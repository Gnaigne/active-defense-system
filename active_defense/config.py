# ============================================================================
# config.py - Cấu hình trung tâm cho hệ thống Active Defense
# ============================================================================
# Tất cả hằng số, ngưỡng phát hiện, đường dẫn log, và regex pattern
# được quản lý tập trung tại đây để dễ dàng điều chỉnh.
# ============================================================================

import os
import re
from dotenv import load_dotenv

# Load biến môi trường từ file .env (nếu có)
load_dotenv()

# ========================== ĐƯỜNG DẪN LOG FILES ============================
# Hai file log chính mà hệ thống sẽ giám sát:
# - auth.log:         Ghi nhận các sự kiện xác thực SSH (login thất bại/thành công)
# - nginx access.log: Ghi nhận tất cả HTTP request đến web server
AUTH_LOG = os.getenv("AUTH_LOG_PATH", "/var/log/auth.log")
NGINX_LOG = os.getenv("NGINX_LOG_PATH", "/var/log/nginx/access.log")

# ========================== DISCORD WEBHOOK =================================
# URL Webhook của Discord channel để nhận cảnh báo.
# Bắt buộc phải cấu hình trong file .env hoặc biến môi trường hệ thống.
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# ========================== NGƯỠNG PHÁT HIỆN (Thresholds) ==================
# SSH_BRUTE_FORCE_THRESHOLD: Số lần đăng nhập thất bại tối đa cho phép
# từ cùng 1 IP trong khoảng SSH_BRUTE_FORCE_WINDOW giây.
# Ví dụ: 5 lần sai trong 60 giây → coi là brute-force.
SSH_BRUTE_FORCE_THRESHOLD = int(os.getenv("SSH_BRUTE_FORCE_THRESHOLD", "5"))
SSH_BRUTE_FORCE_WINDOW = int(os.getenv("SSH_BRUTE_FORCE_WINDOW", "60"))  # giây

# HTTP_FLOOD_THRESHOLD: Số request tối đa cho phép từ 1 IP
# trong khoảng HTTP_FLOOD_WINDOW giây.
# Ví dụ: 100 request trong 10 giây → coi là DoS/Flood.
HTTP_FLOOD_THRESHOLD = int(os.getenv("HTTP_FLOOD_THRESHOLD", "100"))
HTTP_FLOOD_WINDOW = int(os.getenv("HTTP_FLOOD_WINDOW", "10"))  # giây

# ========================== REGEX PATTERNS ==================================
# Mỗi pattern được biên dịch sẵn (re.compile) để tăng hiệu năng khi
# xử lý hàng ngàn dòng log mỗi giây.

# --- SSH Patterns ---
# Pattern bắt dòng log "Failed password" trong auth.log
# Ví dụ log: "Feb 27 10:15:32 server sshd[12345]: Failed password for root from 192.168.1.100 port 22 ssh2"
# Group 'ip' sẽ bắt được: 192.168.1.100
SSH_FAILED_PATTERN = re.compile(
    r"Failed password for (?:invalid user )?\S+ from (?P<ip>\d{1,3}(?:\.\d{1,3}){3})"
)

# --- Nginx Patterns ---
# Pattern bóc tách thông tin từ dòng log Nginx (Combined Log Format)
# Ví dụ log: '192.168.1.100 - - [27/Feb/2026:10:15:32 +0700] "GET /admin/.env HTTP/1.1" 200 512 "-" "curl/7.68"'
# Groups: ip, datetime, method, path, status
NGINX_LOG_PATTERN = re.compile(
    r'(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+-\s+-\s+'           # IP client
    r'\[(?P<datetime>[^\]]+)\]\s+'                              # Timestamp
    r'"(?P<method>\S+)\s+(?P<path>\S+)\s+\S+"\s+'             # HTTP method & path
    r'(?P<status>\d{3})'                                        # Status code
)

# --- Directory/File Traversal Patterns ---
# Danh sách các path nhạy cảm mà attacker thường quét (scan).
# Nếu request truy cập vào bất kỳ path nào chứa các keyword này → nghi vấn.
TRAVERSAL_PATTERNS = re.compile(
    r'(?:'
    r'\.env'                    # File biến môi trường (chứa secrets)
    r'|\.git'                   # Thư mục Git (lộ source code)
    r'|\.htaccess'              # File cấu hình Apache
    r'|\.htpasswd'              # File mật khẩu Apache
    r'|wp-config\.php'          # File config WordPress
    r'|/etc/passwd'             # File user Linux
    r'|/etc/shadow'             # File password hash Linux
    r'|\.\./\.\.'               # Path traversal: ../../
    r'|/proc/self'              # Linux proc filesystem
    r'|/admin'                  # Trang quản trị
    r'|/phpmyadmin'             # phpMyAdmin
    r'|/server-status'          # Apache server status
    r')',
    re.IGNORECASE
)

# --- SQL Injection Patterns ---
# Các keyword SQLi phổ biến xuất hiện trong URL/query string.
# Pattern nhận diện cả dạng URL-encoded (%27 = ', %22 = ", %3D = =).
SQLI_PATTERNS = re.compile(
    r'(?:'
    r"(?:UNION\s+(?:ALL\s+)?SELECT)"                  # UNION SELECT injection
    r"|(?:SELECT\s+.+\s+FROM\s+)"                     # SELECT ... FROM ...
    r"|(?:INSERT\s+INTO\s+)"                           # INSERT INTO
    r"|(?:DELETE\s+FROM\s+)"                           # DELETE FROM
    r"|(?:DROP\s+(?:TABLE|DATABASE))"                  # DROP TABLE/DATABASE
    r"|(?:UPDATE\s+\S+\s+SET\s+)"                     # UPDATE ... SET
    r"|(?:OR\s+1\s*=\s*1)"                             # OR 1=1 (bypass auth)
    r"|(?:AND\s+1\s*=\s*1)"                            # AND 1=1
    r"|(?:'\s*OR\s+')"                                 # ' OR '  (string bypass)
    r"|(?:--\s*$)"                                     # SQL comment (-- )
    r"|(?:/\*.*?\*/)"                                  # Block comment /* */
    r"|(?:;\s*(?:DROP|DELETE|INSERT|UPDATE))"           # Chained query: ;DROP
    r"|(?:SLEEP\s*\()"                                 # Time-based: SLEEP()
    r"|(?:BENCHMARK\s*\()"                             # Time-based: BENCHMARK()
    r"|(?:WAITFOR\s+DELAY)"                            # MSSQL time-based
    r"|(?:%27)|(?:%22)|(?:%3D)"                        # URL-encoded: ' " =
    r")",
    re.IGNORECASE
)

# ========================== WHITELIST =======================================
# Danh sách IP được miễn trừ, KHÔNG BAO GIỜ bị block.
# Ví dụ: IP quản trị, IP nội bộ, IP monitoring.
WHITELISTED_IPS = set(
    ip.strip()
    for ip in os.getenv("WHITELISTED_IPS", "127.0.0.1").split(",")
    if ip.strip()
)

# ========================== CÁC HẰNG SỐ KHÁC ===============================
# Tên loại tấn công (dùng thống nhất trong toàn bộ hệ thống)
ATTACK_SSH_BRUTEFORCE = "SSH Brute-Force"
ATTACK_DIR_TRAVERSAL = "Directory/File Traversal"
ATTACK_SQLI = "SQL Injection"
ATTACK_HTTP_FLOOD = "HTTP DoS/Flood"

# Thời gian chờ giữa các vòng lặp đọc log (giây)
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "0.1"))
