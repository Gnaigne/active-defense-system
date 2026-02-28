#!/bin/bash
# ============================================================================
# entrypoint.sh — Khởi chạy tất cả services trên victim-server
# ============================================================================
# Script này chạy khi container bắt đầu. Nó khởi động lần lượt:
#   1. rsyslog  → sinh file /var/log/auth.log (log SSH)
#   2. SSH      → cho phép attacker thử đăng nhập
#   3. Nginx    → phục vụ HTTP để attacker thử tấn công web
#   4. defender → chạy foreground, giám sát log & phòng thủ
# ============================================================================

set +e  # Không thoát khi có lỗi (rsyslog có thể fail nhưng ta vẫn tiếp)

echo "============================================"
echo "  🖥️  Victim Server — Starting Services"
echo "============================================"

# --- 1. Chuẩn bị log files ---
echo "[1/4] Preparing log files..."
mkdir -p /var/log/nginx
touch /var/log/auth.log /var/log/nginx/access.log
chmod 666 /var/log/auth.log
echo "  ✓ Log files ready → /var/log/auth.log, /var/log/nginx/access.log"

# --- 2. Khởi động SSH daemon ---
echo "[2/4] Starting SSH server..."
# Cấu hình sshd ghi log trực tiếp vào file (không cần rsyslog trong Docker)
# -E: redirect sshd log vào file thay vì syslog
# -D: foreground mode, & đẩy vào background
/usr/sbin/sshd -D -E /var/log/auth.log &
sleep 1
echo "  ✓ SSH server started (port 22)"
echo "  ✓ SSH logs → /var/log/auth.log (direct file logging)"
echo "  ✓ User: admin / Password: password123"

# --- 3. Khởi động Nginx ---
echo "[3/4] Starting Nginx..."
nginx
sleep 1
echo "  ✓ Nginx started (port 80)"
echo "  ✓ Nginx access log → /var/log/nginx/access.log"

# --- 4. Khởi chạy Active Defense System ---
echo "[4/4] Starting Active Defense System..."
echo "============================================"
echo "  🛡️  All services running. Defender active."
echo "  Press Ctrl+C to stop."
echo "============================================"

# Chạy defender.py ở foreground (giữ container sống)
# KHÔNG dùng --dry-run vì trong Docker ta có quyền root
cd /opt/defender
exec python3 defender.py
