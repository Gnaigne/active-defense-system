# ============================================================================
# Dockerfile — victim-server (Máy chủ nạn nhân)
# ============================================================================
# Container này mô phỏng một máy chủ Linux chạy web (Nginx) và SSH.
# Tool defender.py sẽ giám sát log và tự động phòng thủ.
#
# Base: Ubuntu 22.04
# Services: Nginx, OpenSSH Server, Python3 + defender.py
# ============================================================================

FROM ubuntu:22.04

# Tránh interactive prompt khi cài đặt packages
ENV DEBIAN_FRONTEND=noninteractive

# === BƯỚC 1: Cài đặt các service cần thiết ===
# - openssh-server : SSH daemon để attacker thử brute-force
# - nginx          : Web server để attacker thử Traversal, SQLi, Flood
# - iptables       : Tường lửa để defender.py chặn IP
# - python3 + pip  : Runtime cho defender.py
# - rsyslog        : Sinh auth.log (ghi log SSH)
# - iproute2       : Lệnh ip (debug network)
# - procps         : Lệnh ps (debug process)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    nginx \
    iptables \
    python3 \
    python3-pip \
    rsyslog \
    iproute2 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# === BƯỚC 2: Cấu hình SSH ===
# Tạo thư mục run/sshd (yêu cầu bởi sshd)
RUN mkdir -p /run/sshd

# Tạo user "admin" với password yếu để demo brute-force
# ⚠️ CHỈ DÙNG CHO MỤC ĐÍCH DEMO — không dùng trong production!
RUN useradd -m -s /bin/bash admin && \
    echo "admin:password123" | chpasswd

# Cho phép đăng nhập SSH bằng password (mặc định Ubuntu tắt)
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    echo "MaxAuthTries 100" >> /etc/ssh/sshd_config

# === BƯỚC 3: Cấu hình Nginx ===
# Copy file cấu hình Nginx tùy chỉnh (bật access log)
COPY docker/victim/nginx.conf /etc/nginx/nginx.conf

# Tạo một trang web đơn giản để attacker có mục tiêu
RUN mkdir -p /var/www/html && \
    echo '<html><head><title>Victim Server</title></head>' \
         '<body><h1>Welcome to Victim Server</h1>' \
         '<p>This server is protected by Active Defense System.</p>' \
         '</body></html>' > /var/www/html/index.html

# === BƯỚC 4: Cài đặt defender.py ===
# Tạo thư mục làm việc
WORKDIR /opt/defender

# Copy requirements trước (tận dụng Docker layer cache)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY active_defense/ ./active_defense/
COPY defender.py .

# === BƯỚC 5: Copy file .env (cấu hình) ===
COPY .env .env

# === BƯỚC 6: Copy entrypoint script ===
COPY docker/victim/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# === BƯỚC 7: Expose ports ===
# SSH (22) và HTTP (80) để attacker có thể kết nối
EXPOSE 22 80

# === BƯỚC 8: Khởi chạy ===
# Entrypoint sẽ start tất cả services và chạy defender.py
ENTRYPOINT ["/entrypoint.sh"]
