# 🛡️ Active Defense System — Mini IPS for Linux Servers

Hệ thống phòng thủ chủ động (Host-based IPS) chạy trên Linux, giám sát log SSH và Nginx theo thời gian thực, tự động phát hiện 4 loại tấn công phổ biến (SSH Brute-Force, Directory Traversal, SQL Injection, HTTP Flood), chặn IP bằng iptables và gửi cảnh báo qua Discord.

---

📚 **Tài liệu dự án:**
- 👉 [Xem Tài liệu Kiến trúc (ARCHITECTURE.md)](ARCHITECTURE.md)
- 👉 Xem Nhật ký Vibe Coding *(link sẽ được cập nhật)*

---

## 📋 Yêu cầu môi trường (Prerequisites)

- **Docker** (bao gồm Docker Compose plugin) — [Hướng dẫn cài đặt](https://docs.docker.com/get-docker/)
- **Git** — để clone source code

Không cần cài Python, Nginx, hay bất kỳ phần mềm nào khác — Docker đã đóng gói tất cả.

---

## 🚀 Cài đặt & Khởi chạy

### ⭐ Cách tối ưu: GitHub Codespaces (Khuyến nghị)

Không cần cài bất kỳ phần mềm nào. Chỉ cần trình duyệt:

1. Vào repo trên GitHub → nhấn nút **"Code"** → **"Codespaces"** → **"Create codespace on main"**
2. Đợi ~2 phút để Codespaces khởi tạo môi trường (Linux + Docker tự có sẵn)
3. Trong terminal Codespaces, chạy:

```bash
docker compose up --build -d
```

4. Xong! Hệ thống đã chạy. Chuyển sang mục **Kịch bản Demo** bên dưới để test.

> 💡 **Lưu ý:** Sau khi test xong, vào https://github.com/codespaces → nhấn `...` → **Stop codespace** để không bị tính giờ (mỗi account GitHub Free có 60h/tháng, dư sức test).

---

### 🐧 Cách khác: Chạy trên máy local

**Linux:** Cài Docker + Git → clone repo → chạy `docker compose up --build -d`.

**Windows:** Cần bật ảo hóa phần cứng (Virtualization) trong BIOS, sau đó cài [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) (sẽ tự cài WSL2). Rồi chạy tương tự.

```bash
git clone <REPO_URL>
cd active-defense-system
docker compose up --build -d
```

> ✅ **File `.env` đã có sẵn trong repo** (bao gồm Discord Webhook URL). Không cần cấu hình gì thêm.
>
> 💬 Cảnh báo sẽ được gửi đến Discord server của dự án. [Join tại đây](https://discord.gg/YDSPtmUhw5) (vào channel **#security-alerts**) để xem alert real-time.

Hệ thống sẽ tạo 2 container:

| Container | IP | Vai trò |
|-----------|-----|---------|
| `victim-server` | 172.20.0.10 | Máy chủ nạn nhân (Nginx + SSH + defender.py + iptables) |
| `attacker-machine` | 172.20.0.20 | Máy tấn công (hydra, curl, ab) |

Kiểm tra trạng thái:

```bash
docker ps                           # Xem container đang chạy
docker logs victim-server            # Xem log defender.py
```

Tắt hệ thống:

```bash
docker compose down
```

---

## 🎯 Kịch bản Demo (How to Test)

Hệ thống hỗ trợ **4 loại tấn công**. Có 2 cách test:

### Cách 1: Chạy script tự động 

Script `run_test.sh` tự động restart victim → exec attack → hiện log defender:

```bash
# Cho quyền thực thi (chỉ cần lần đầu)
chmod +x run_test.sh

# Test từng loại tấn công
./run_test.sh traversal       # Directory/File Traversal
./run_test.sh sqli            # SQL Injection
./run_test.sh flood           # HTTP DoS/Flood
./run_test.sh bruteforce      # SSH Brute-Force

# Chạy cả 4 liên tiếp (tự động restart giữa mỗi lần)
./run_test.sh all
```

> 💡 Trên Codespaces không cần `sudo`. Trên máy local có thể cần thêm `sudo` trước lệnh.

---

### Cách 2: Chạy thủ công (Interactive)

Mở **3 terminal** riêng biệt:

#### Terminal 1 — Xem log defender real-time trên victim

```bash
docker exec -it victim-server bash
tail -f /var/log/auth.log /var/log/nginx/access.log
```

#### Terminal 2 — Chui vào máy attacker

```bash
docker exec -it attacker-machine bash
```

#### Terminal 3 — Dùng để restart victim khi IP bị block

```bash
docker restart victim-server
```

> ⚠️ **Lưu ý quan trọng:** Sau mỗi lần tấn công bị phát hiện, defender sẽ block IP attacker. Để test tiếp loại khác, phải restart victim bằng Terminal 3 để reset iptables.

---

Từ **Terminal 2** (trong attacker), chạy các lệnh sau:

#### 📂 Attack 1 — Directory/File Traversal

```bash
# Dùng script có sẵn
./attack_scripts.sh traversal

# Hoặc chạy thủ công bằng curl
curl http://victim-server/.env
curl http://victim-server/.git/config
curl http://victim-server/../../etc/passwd
curl http://victim-server/admin/.env
curl http://victim-server/phpmyadmin/
```

#### 💉 Attack 2 — SQL Injection

```bash
# Dùng script có sẵn
./attack_scripts.sh sqli

# Hoặc chạy thủ công
curl "http://victim-server/search?q=1%20OR%201=1"
curl "http://victim-server/api/users?id=1%20UNION%20SELECT%20*%20FROM%20users"
curl "http://victim-server/login?user=admin'%20OR%20'1'='1"
curl "http://victim-server/products?category=1;%20DROP%20TABLE%20users"
curl "http://victim-server/api?id=SLEEP(5)"
```

#### 🌊 Attack 3 — HTTP DoS/Flood

```bash
# Dùng script có sẵn
./attack_scripts.sh flood

# Hoặc chạy thủ công bằng Apache Bench
# Gửi 200 request, 50 đồng thời → vượt ngưỡng 100 req/10s
ab -n 200 -c 50 http://victim-server/
```

#### 🔐 Attack 4 — SSH Brute-Force

```bash
# Dùng script có sẵn
./attack_scripts.sh bruteforce

# Hoặc chạy thủ công bằng hydra
hydra -L /opt/attack/usernames.txt -P /opt/attack/passwords.txt -t 4 -V -f ssh://victim-server

# Hoặc thử SSH tay (sai password 5 lần liên tiếp sẽ bị block)
sshpass -p 'wrongpass1' ssh -o StrictHostKeyChecking=no admin@victim-server
sshpass -p 'wrongpass2' ssh -o StrictHostKeyChecking=no admin@victim-server
sshpass -p 'wrongpass3' ssh -o StrictHostKeyChecking=no admin@victim-server
sshpass -p 'wrongpass4' ssh -o StrictHostKeyChecking=no admin@victim-server
sshpass -p 'wrongpass5' ssh -o StrictHostKeyChecking=no admin@victim-server
```

---

### Kết quả mong đợi

Sau mỗi cuộc tấn công, trên **Terminal 1** (victim) sẽ hiện:

```
⚠ Traversal Detected: 172.20.0.20 → /.env
🚨 TẤN CÔNG PHÁT HIỆN!
   Loại  : Directory/File Traversal
   IP    : 172.20.0.20
🔒 ĐÃ BLOCK: 172.20.0.20 (iptables -A INPUT -s 172.20.0.20 -j DROP)
📨 Đã gửi cảnh báo Discord: Directory/File Traversal — 172.20.0.20
```

Đồng thời, **Discord channel** sẽ nhận được embed cảnh báo với đầy đủ thông tin.

---

## 📁 Cấu trúc Thư mục (Folder Structure)

```
active-defense-system/
│
├── defender.py                      # 🚀 Entry point chính — CLI, orchestrator
├── requirements.txt                 # 📦 Thư viện Python (rich, requests, dotenv)
├── .env.example                     # 📝 Mẫu cấu hình (copy thành .env)
├── .env                             # 🔑 Cấu hình thật (Discord Webhook, ngưỡng)
├── run_test.sh                      # 🧪 Script test tự động trên host
│
├── active_defense/                  # 📂 Package Python — logic phòng thủ
│   ├── __init__.py
│   ├── config.py                    #   ⚙️ Cấu hình trung tâm: regex, ngưỡng, path
│   ├── monitor.py                   #   👁️ Giám sát log real-time (tail -f, Queue)
│   ├── detector.py                  #   🔍 Phát hiện 4 loại tấn công (regex, sliding window)
│   ├── firewall.py                  #   🔒 Quản lý iptables (block/unblock IP)
│   └── alerter.py                   #   📨 Gửi cảnh báo Discord Webhook
│
├── docker/
│   ├── victim/
│   │   ├── Dockerfile               #   🖥️ Image victim: Ubuntu + Nginx + SSH + Python
│   │   ├── entrypoint.sh            #   🔧 Script khởi chạy services trong container
│   │   └── nginx.conf               #   🌐 Cấu hình Nginx (access log format)
│   └── attacker/
│       ├── Dockerfile               #   💀 Image attacker: Ubuntu + hydra + curl + ab
│       └── attack_scripts.sh        #   ⚔️ 4 script tấn công mẫu
│
├── docker-compose.yml               # 🐳 Orchestration: 2 container + network
├── ARCHITECTURE.md                  # 📐 Tài liệu kiến trúc hệ thống
└── README.md                        # 📖 File này — hướng dẫn sử dụng
```
