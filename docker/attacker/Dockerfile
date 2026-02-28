# ============================================================================
# Dockerfile — attacker-machine (Máy tấn công)
# ============================================================================
# Container này đóng vai kẻ tấn công, được trang bị các công cụ pentest
# phổ biến để mô phỏng 4 kịch bản tấn công vào victim-server.
#
# Công cụ cài sẵn:
#   • hydra        → SSH Brute-Force (thử hàng loạt password)
#   • curl         → Directory Traversal & SQL Injection (gửi HTTP request)
#   • apache2-utils (ab) → HTTP DoS/Flood (gửi request ồ ạt)
#   • nmap         → Scan port (trinh sát)
#   • sqlmap       → SQL Injection tự động (nâng cao)
#   • sshpass      → SSH tự động nhập password (hỗ trợ script)
# ============================================================================

FROM ubuntu:22.04
 
ENV DEBIAN_FRONTEND=noninteractive

# === Cài đặt các công cụ tấn công ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    hydra \
    curl \
    apache2-utils \
    nmap \
    sshpass \
    openssh-client \
    iputils-ping \
    iproute2 \
    dnsutils \
    wget \
    vim \
    && rm -rf /var/lib/apt/lists/*

# === Tạo thư mục làm việc cho attacker ===
WORKDIR /opt/attack

# === Tạo wordlist password cho hydra ===
# File này chứa danh sách password phổ biến để brute-force SSH
RUN echo -e "123456\npassword\nadmin\nroot\npassword123\n12345678\n\
qwerty\nabc123\nletmein\nwelcome\nmonkey\nmaster\ndragon\nlogin\n\
princess\nfootball\nshadow\nsunshine\ntrustno1\niloveyou" > /opt/attack/passwords.txt

# === Tạo wordlist username cho hydra ===
RUN echo -e "root\nadmin\nuser\ntest\nubuntu\nwww-data\nnginx\n\
ftpuser\nmysql\npostgres" > /opt/attack/usernames.txt

# === Tạo script tấn công mẫu (tiện cho demo) ===
COPY docker/attacker/attack_scripts.sh /opt/attack/attack_scripts.sh
RUN chmod +x /opt/attack/attack_scripts.sh

# Giữ container chạy (chờ người dùng exec vào)
CMD ["sleep", "infinity"]
