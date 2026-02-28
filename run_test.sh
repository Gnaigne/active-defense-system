#!/bin/bash
# ============================================================================
# run_test.sh — Script test tự động chạy trên HOST
# ============================================================================
# Tự động restart victim → exec attack trên attacker → xem log defender.
# Giải quyết vấn đề: victim block IP sau mỗi attack → cần restart giữa các lần.
#
# Cách dùng:
#   ./run_test.sh traversal       → Test Directory Traversal
#   ./run_test.sh sqli            → Test SQL Injection
#   ./run_test.sh flood           → Test HTTP DoS/Flood
#   ./run_test.sh bruteforce      → Test SSH Brute-Force
#   ./run_test.sh all             → Chạy lần lượt cả 4 (có restart giữa mỗi lần)
# ============================================================================

set -e

VICTIM="victim-server"
ATTACKER="attacker-machine"
WAIT_SECONDS=8    # Thời gian chờ victim khởi động lại

# Màu console
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- Hàm tiện ích ---
banner() {
    echo ""
    echo -e "${BOLD}${CYAN}============================================${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}============================================${NC}"
    echo ""
}

restart_victim() {
    echo -e "${YELLOW}↻ Restarting victim-server (reset iptables + defender)...${NC}"
    sudo docker restart $VICTIM > /dev/null 2>&1
    echo -e "${YELLOW}  Waiting ${WAIT_SECONDS}s for services to start...${NC}"
    sleep $WAIT_SECONDS
    # Ghi nhận thời điểm restart để lọc log chính xác
    RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo -e "${GREEN}✓ Victim ready.${NC}"
    echo ""
}

show_defender_log() {
    echo ""
    echo -e "${BOLD}--- Defender Log (since restart) ---${NC}"
    sudo docker logs --since "$RESTART_TS" $VICTIM 2>&1 | grep -E "⚠|🚨|🔒|📨|Loại|IP    " | head -10
    echo -e "${BOLD}------------------------------------${NC}"
    echo ""
}

run_attack() {
    local attack_name="$1"
    local display_name="$2"

    banner "⚔️  $display_name"
    restart_victim
    echo -e "${RED}>>> Executing attack from attacker-machine...${NC}"
    echo ""
    sudo docker exec $ATTACKER ./attack_scripts.sh "$attack_name"
    sleep 2
    show_defender_log
}

# --- Main ---
case "${1:-help}" in
    traversal|tr)
        run_attack "traversal" "Directory/File Traversal"
        ;;
    sqli|sql)
        run_attack "sqli" "SQL Injection"
        ;;
    flood|dos)
        run_attack "flood" "HTTP DoS/Flood"
        ;;
    bruteforce|bf)
        run_attack "bruteforce" "SSH Brute-Force"
        ;;
    all)
        banner "🏁 FULL TEST — 4 ATTACK SCENARIOS"
        echo -e "${YELLOW}Sẽ tự động restart victim giữa mỗi lần tấn công.${NC}"
        echo ""

        run_attack "traversal"  "1/4 — Directory/File Traversal"
        run_attack "sqli"       "2/4 — SQL Injection"
        run_attack "flood"      "3/4 — HTTP DoS/Flood"
        run_attack "bruteforce" "4/4 — SSH Brute-Force"

        banner "✅ ALL 4 ATTACKS COMPLETED"
        echo -e "${GREEN}Kiểm tra Discord channel để xem 4 cảnh báo.${NC}"
        echo ""
        ;;
    *)
        banner "🛡️  Active Defense — Test Runner"
        echo "  Cách dùng: ./run_test.sh <command>"
        echo ""
        echo "  Commands:"
        echo "    traversal  (tr)   Directory Traversal"
        echo "    sqli       (sql)  SQL Injection"
        echo "    flood      (dos)  HTTP DoS/Flood"
        echo "    bruteforce (bf)   SSH Brute-Force"
        echo "    all               Chạy cả 4 (auto-restart)"
        echo ""
        ;;
esac
