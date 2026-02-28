# 📐 Tài liệu Kiến trúc — Active Defense System

## 1. Vấn đề giải quyết

Bất kỳ máy chủ Linux nào có IP Public đều liên tục bị quét tự động bởi botnet và kẻ tấn công. Mỗi ngày, một server trung bình nhận **hàng nghìn** lần thử đăng nhập SSH sai, request dò quét file nhạy cảm (`.env`, `.git`), và các payload SQL Injection nhúng trong URL.

Tường lửa tĩnh (static rules) **không đủ** vì kẻ tấn công thay đổi IP liên tục. Cần một hệ thống **phòng thủ chủ động (Host-based IPS)** ngay trên máy chủ, có khả năng:

- **Giám sát** log hệ thống theo thời gian thực.
- **Phát hiện** hành vi bất thường bằng phân tích mẫu (pattern matching).
- **Tự động chặn** IP vi phạm ở tầng kernel (iptables) — cắt kết nối ngay lập tức.
- **Cảnh báo** quản trị viên qua kênh thông báo (Discord) để phản ứng kịp thời.

Đây chính là triết lý **Defense in Depth** — phòng thủ nhiều lớp, ngay tại host.

---

## 2. Tại sao chọn Tech Stack / Công cụ

| Công cụ | Lý do chọn |
|---------|-----------|
| **Python 3** | Nhanh để prototype, xử lý văn bản và Regex cực tốt, thư viện `rich` cho console đẹp, `requests` cho HTTP webhook. |
| **Docker** | Đóng gói toàn bộ môi trường (victim + attacker) vào 1 lệnh duy nhất. Giám khảo chỉ cần `docker compose up` là có lab hoàn chỉnh, không cài đặt gì thêm. |
| **iptables** | Tường lửa native của Linux kernel. Chặn IP ở tầng thấp nhất (network layer) — packet bị DROP trước khi đến application, hiệu quả tối đa. |
| **Nginx** | Web server phổ biến nhất, sinh access log chuẩn (Combined Log Format) dễ parse bằng regex. |
| **Discord Webhook** | API đơn giản (1 HTTP POST), không cần authentication phức tạp, hiển thị embed đẹp, miễn phí. |

---

## 3. Luồng hoạt động chính (System Flow)

```
                        ┌──────────────────────────────────────────────┐
                        │          victim-server (Docker)              │
                        │                                              │
  Attacker ──────┐      │   Nginx (port 80)  ──→  access.log          │
  (curl, ab,     │      │   SSH   (port 22)  ──→  auth.log            │
   hydra)        │      │                            │                 │
                 ▼      │                            ▼                 │
          ┌──────────┐  │  ┌─────────────────────────────────────┐     │
          │ Request  │──┼─→│  BƯỚC 1: MONITOR (monitor.py)      │     │
          │ / Login  │  │  │  Thread tail -f mỗi file log       │     │
          └──────────┘  │  │  Dòng mới → đẩy vào Queue          │     │
                        │  └──────────────┬──────────────────────┘     │
                        │                 │ Queue(log_type, line)      │
                        │                 ▼                            │
                        │  ┌─────────────────────────────────────┐     │
                        │  │  BƯỚC 2: DETECT (detector.py)       │     │
                        │  │  Regex match 4 loại tấn công:       │     │
                        │  │   • SSH Brute-Force (≥5 fail/60s)   │     │
                        │  │   • Directory Traversal (.env,.git) │     │
                        │  │   • SQL Injection (UNION, OR 1=1)   │     │
                        │  │   • HTTP Flood (≥100 req/10s)       │     │
                        │  └──────────────┬──────────────────────┘     │
                        │                 │ callback(ip, type, line)   │
                        │                 ▼                            │
                        │  ┌─────────────────────────────────────┐     │
                        │  │  BƯỚC 3: ACT (firewall.py)          │     │
                        │  │  iptables -A INPUT -s <IP> -j DROP  │     │
                        │  │  → Chặn IP ở tầng kernel            │     │
                        │  └──────────────┬──────────────────────┘     │
                        │                 │                            │
                        │                 ▼                            │
                        │  ┌─────────────────────────────────────┐     │
                        │  │  BƯỚC 4: ALERT (alerter.py)         │     │
                        │  │  POST JSON → Discord Webhook        │     │
                        │  │  Embed: IP, loại tấn công, log,     │     │
                        │  │         thời gian, trạng thái block  │     │
                        │  └─────────────────────────────────────┘     │
                        │                                              │
                        └──────────────────────────────────────────────┘
```

**Giải thích luồng:**

1. **Monitor** — Hai thread Python liên tục đọc `auth.log` (SSH) và `access.log` (Nginx) bằng kỹ thuật `tail -f` thuần Python. Mỗi dòng log mới được đẩy vào một `Queue` chung (mô hình Producer-Consumer).

2. **Detect** — Thread detector lấy dòng log từ Queue, dùng Regex đã biên dịch sẵn (`re.compile`) để nhận diện 4 kịch bản tấn công. Với SSH Brute-Force và HTTP Flood, hệ thống dùng thuật toán **Sliding Window** (cửa sổ thời gian trượt) để đếm tần suất theo IP.

3. **Act** — Khi phát hiện vi phạm, gọi `subprocess.run(["iptables", ...])` để thêm rule DROP. IP được validate bằng regex trước khi đưa vào lệnh (phòng command injection). Có kiểm tra whitelist và trùng lặp.

4. **Alert** — Gửi Discord Embed chứa đầy đủ thông tin (thời gian, IP, loại tấn công, trích xuất log gốc) qua HTTP POST đến Webhook URL. Mỗi loại tấn công có màu và emoji riêng.
