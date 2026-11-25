# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Các anti-pattern phát hiện trong `01-localhost-vs-production/develop/app.py`:

1. **Hardcode secrets trong source code (`app.py` dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - Nếu push lên Git repository (đặc biệt repo public), key và mật khẩu database bị lộ ngay lập tức và còn lưu vĩnh viễn trong lịch sử git.
2. **Hardcode cấu hình ứng dụng (`app.py` dòng 21–22):**
   - `DEBUG = True` và `MAX_TOKENS = 500` viết cứng trong code, không tách cấu hình theo môi trường (dev/staging/production).
3. **Dùng `print()` thay cho structured logging và in cả secret ra log (`app.py` dòng 33–34, 38):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key thẳng ra stdout/log hệ thống; log dạng text tự do khó parse/truy vấn trên log aggregator (Loki, Datadog, CloudWatch).
4. **Không có endpoint health check / readiness (`app.py` dòng 42–43):**
   - Thiếu `GET /health` và `GET /ready`, nên cloud platform hoặc load balancer không biết khi nào container chết để restart hay khi nào sẵn sàng nhận traffic.
5. **Bind cứng `host="localhost"`, cố định `port=8000` và bật `reload=True` (`app.py` dòng 49–54):**
   - `host="localhost"` chỉ lắng nghe loopback bên trong máy/container nên traffic từ ngoài container không vào được; `port=8000` cố định bỏ qua biến `PORT` do cloud platform (Railway/Render) cấp; `reload=True` tiêu tốn tài nguyên và không an toàn trong production.
6. **Không có cơ chế Graceful Shutdown & CORS:**
   - Khi nhận `SIGTERM` lúc deploy/scale-down, process dừng đột ngột có thể cắt ngang request đang xử lý; không quản lý vòng đời startup/shutdown (`lifespan`).

**Đối chiếu cụ thể anti-pattern đã sửa giữa `develop/app.py` và `production/`:**
- Hardcode secret & config ở `develop/app.py` dòng 17–22 (`OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"`) được thay bằng `production/config.py` dòng 14–46 (`Settings` đọc từ `os.getenv(...)`, kiểm tra `AGENT_API_KEY` bắt buộc khi `environment == "production"` trong `validate()`).
- Bind cứng `host="localhost"`, `port=8000`, `reload=True` ở `develop/app.py` dòng 49–54 được sửa trong `production/app.py` dòng 194–199 thành `host=settings.host` (mặc định `0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug`.
- Bổ sung `/health` (dòng 135–149), `/ready` (dòng 152–161), `lifespan` + `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 39–68, 180–189) và log JSON bằng `json.dumps(...)` (dòng 49–55, 111–122) không log secret.

---

### Exercise 1.2: Chạy bản develop

Chạy `python app.py` trong `01-localhost-vs-production/develop/` (WSL2 Ubuntu):

```bash
curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả trả về:

```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:24:48 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Kiểm chứng log phía server cho thấy `print()` đã in thẳng secret ra log và gửi JSON body bị `422`:

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
INFO:     127.0.0.1:60070 - "POST /ask?question=Hello HTTP/1.1" 200 OK
INFO:     127.0.0.1:60074 - "POST /ask HTTP/1.1" 422 Unprocessable Content
```

---

### Exercise 1.3: Chạy bản production và bảng so sánh

Chạy `python app.py` trong `01-localhost-vs-production/production/` (tạo `.env` tạm từ `.env.example`, kiểm tra xong xóa `.env` để không lọt secret):

```text
GET /health -> HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:24:50.792636+00:00"}

GET /ready -> HTTP/1.1 200 OK
{"ready":true}

POST /ask (JSON {"question": "Hello"}) -> HTTP/1.1 200 OK
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}
```

Bảng so sánh `develop/app.py` vs `production/app.py`:

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| **Config & Secrets** | Hardcode trực tiếp (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS`) | Đọc từ biến môi trường qua `Settings` (`os.getenv`), có `validate()` | Thay đổi cấu hình theo môi trường (dev/staging/prod) mà không sửa code; tránh lộ secrets khi push lên Git. |
| **Host & Port** | Cố định `host="localhost"`, `port=8000`, `reload=True` | `HOST` mặc định `0.0.0.0`, `PORT` từ env var, `reload=settings.debug` | `0.0.0.0` mới nhận được traffic từ ngoài container; cloud platform cấp `PORT` động khi deploy; tắt `reload` tránh tốn CPU/RAM và rủi ro bảo mật. |
| **Health Check** | Không có | Có `GET /health` (liveness) và `GET /ready` (readiness) | Platform/load balancer biết khi nào container còn sống để giữ/restart và khi nào đã sẵn sàng nhận traffic. |
| **Logging** | `print()` tự do, in cả `OPENAI_API_KEY` ra màn hình | `logging` với định dạng JSON (`json.dumps`), không log secrets | Log JSON chuẩn hóa giúp hệ thống tập trung (Loki, Datadog) parse, filter và tạo alert chính xác mà không làm rò rỉ thông tin nhạy cảm. |
| **Shutdown** | Thoát đột ngột khi tắt process | Quản lý vòng đời bằng `lifespan` + bắt `SIGTERM` (`handle_sigterm`) | Khi container restart/scale-down, request đang xử lý kịp hoàn thành trả về 200 và đóng kết nối sạch sẽ, không mất dữ liệu người dùng. |
| **CORS & Input** | Không cấu hình CORS; `/ask` nhận query param | Có `CORSMiddleware` đọc `ALLOWED_ORIGINS`; `/ask` nhận JSON body và validate trả `422` nếu thiếu `question` | Kiểm soát domain frontend được phép gọi API và chuẩn hóa contract JSON API. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

Trả lời 4 câu hỏi từ `02-docker/develop/Dockerfile`:

1. **Base image là gì?**
   - `python:3.11` (`FROM python:3.11` ở dòng 8) — bản Python đầy đủ dựa trên Debian, gồm cả trình biên dịch và các thư viện hệ thống (~1 GB).
2. **Working directory là gì?**
   - `/app` (`WORKDIR /app` ở dòng 11) — thư mục làm việc mặc định bên trong container cho các lệnh `COPY`, `RUN`, `CMD` phía sau.
3. **Tại sao `COPY requirements.txt` trước `COPY app.py`?**
   - Để tận dụng **Docker layer cache**: mỗi chỉ thị trong Dockerfile tạo một layer cache. `requirements.txt` ít thay đổi hơn source code, nên nếu đặt trước và chạy `RUN pip install --no-cache-dir -r requirements.txt` trước khi `COPY ... app.py`, khi sửa code Python thì Docker dùng lại cache của layer cài thư viện thay vì phải `pip install` lại từ đầu.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` đặt lệnh/tham số mặc định khi container khởi chạy và **có thể bị ghi đè** dễ dàng bằng đối số truyền vào cuối lệnh `docker run <image> <command>`.
   - `ENTRYPOINT` cố định file thực thi chính của container (khó bị ghi đè hơn, chỉ đổi khi dùng `--entrypoint`); khi kết hợp cả hai, `ENTRYPOINT` là lệnh chính còn `CMD` đóng vai trò tham số mặc định cho lệnh đó.

---

### Exercise 2.2: Build và run `my-agent:develop`

Build từ gốc repo (`docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`), chạy container với `-p 8000:8000` và test:

```text
GET /health -> HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.3,"container":true}

POST /ask?question=What%20is%20Docker%3F -> HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build và so sánh image size

Phân tích `02-docker/production/Dockerfile`:
- **Stage 1 (`builder`):** Dùng `python:3.11-slim AS builder`, cài `gcc` và `libpq-dev` để biên dịch các package có phần mở rộng C, rồi chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`. Stage này không được đưa vào image cuối.
- **Stage 2 (`runtime`):** Bắt đầu từ một image `python:3.11-slim` sạch hoàn toàn, tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local` cùng `main.py` và `utils/mock_llm.py`, thiết lập `USER appuser`, `HEALTHCHECK` và `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]`.
- **Vì sao image nhỏ hơn:** Không mang theo image nền `python:3.11` cồng kềnh (~1 GB), cũng loại bỏ hoàn toàn `gcc`, `libpq-dev`, `binutils`, header files và cache `apt`/`pip` của Stage 1 ra khỏi image cuối cùng.

Số đo thực tế bằng `docker images` và `docker image inspect` trên máy:
- **Develop (`my-agent:develop`):** `1.67 GB` (`1,667,779,923` bytes ≈ `1590.52 MB` MiB / `1667.78 MB` decimal)
- **Production (`my-agent:advanced`):** `240 MB` (`239,815,303` bytes ≈ `228.71 MB` MiB / `239.82 MB` decimal)
- **Chênh lệch (giảm):** **`85.6%`** (nhỏ hơn ~6.95 lần, đạt chuẩn `< 500 MB`).

---

### Exercise 2.4: Docker Compose stack và kết quả test qua Nginx

**Sơ đồ kiến trúc stack (`02-docker/production/docker-compose.yml` & `nginx/nginx.conf`):**

```text
Client
  │  HTTP :80 (HTTPS :443)
  ▼
[ nginx ]  (nginx:alpine — Reverse Proxy, Rate limit 10r/s, Security headers)
  │  proxy_pass http://agent_backend (network: internal)
  ▼
[ agent ]  (FastAPI / uvicorn :8000 — target: runtime, depends_on redis & qdrant healthy)
  ├──► [ redis ]   (redis:7-alpine :6379, volume redis_data, healthcheck redis-cli ping)
  └──► [ qdrant ]  (qdrant/qdrant:v1.9.0 :6333, volume qdrant_data, healthcheck /dev/tcp)
```

Cách giao tiếp: Các service nằm chung bridge network `internal`; chỉ `nginx` mở port `80`/`443` ra ngoài host, còn `agent`, `redis`, `qdrant` chỉ giao tiếp nội bộ qua tên service (`redis://redis:6379/0`, `http://qdrant:6333`). `agent` chỉ khởi động sau khi `redis` và `qdrant` đạt trạng thái `healthy`.

**Kết quả test thực tế qua Nginx (`http://localhost`):**

```text
$ docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml ps
NAME                       IMAGE                   SERVICE   STATUS
k5-day14-docker-agent-1    k5-day14-docker-agent   agent     Up 1 second (health: starting)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            nginx     Up 1 second                      0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    qdrant    Up 12 seconds (healthy)          6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          redis     Up 12 seconds (healthy)          6379/tcp

GET http://localhost/health -> HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.5,"version":"2.0.0","timestamp":"2026-11-25T09:37:20.687794"}

POST http://localhost/ask -> HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 & 3.2: Deploy `06-lab-complete/` lên Render (Free Tier)

- **Public URL:** `https://k5-l3a-day14-nguyentronghuong.onrender.com`
- **Nền tảng:** Render Web Service (`runtime: docker`, Root Directory: `06-lab-complete`, Region: `Singapore`) kết nối Render Key Value (Redis).
- **Screenshots:**
  - `screenshots/dashboard.png`
  - `screenshots/running.png`
  - `screenshots/test.png`
- **Kết quả kiểm tra URL public:**

```text
GET  /health -> HTTP/2 200 {"status":"ok","environment":"production","uptime_seconds":154.9}
GET  /ready  -> HTTP/2 200 {"ready":true}
POST /ask (no X-API-Key) -> HTTP/2 401 {"detail":"Invalid or missing API key. Provide header: X-API-Key"}
POST /ask (with X-API-Key) -> HTTP/2 200 (xem ảnh screenshots/test.png)
```

### So sánh `railway.toml` và `render.yaml` (Exercise 3.2)

| Khía cạnh | `railway.toml` | `render.yaml` | Vì sao khác nhau |
|---|---|---|---|
| **Định dạng & phạm vi** | TOML (`[build]`, `[deploy]`), cấu hình cho **1 service** hiện tại | YAML (`services:` list), chuẩn **Infrastructure-as-Code (Blueprint)** khai báo cả Web Service lẫn Redis (`type: keyvalue`/`redis`) trong cùng một file | Railway quản lý từng service riêng trong Project và nối biến bằng reference `${{Redis.REDIS_URL}}`, còn Render Blueprint cho phép định nghĩa toàn bộ topology đa dịch vụ ở một file. |
| **Build & Runtime** | `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` | `runtime: docker` (hoặc `runtime: python` kèm `buildCommand` / `startCommand`), chỉ rõ `plan: free`, `region: singapore` | Render yêu cầu khai báo tường minh gói tài nguyên (`plan`) và vùng (`region`) trong Blueprint; Railway chọn tài nguyên theo usage trên dashboard. |
| **Health check** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` | Cùng mục đích kiểm tra liveness nhưng khác cú pháp theo schema từng nền tảng. |
| **Quản lý Secrets & Env** | Không khai báo env/secret trong `railway.toml`; đặt qua CLI (`railway variables set`) hoặc Dashboard | Khai báo trực tiếp `envVars:` trong YAML; secret bắt buộc dùng `generateValue: true` hoặc `sync: false`, và nối Redis qua `fromService:` | Vì `render.yaml` được commit lên Git, Render cung cấp cơ chế `sync: false` / `generateValue: true` để tránh lộ secret trong file YAML. |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD của Cloud Run đi qua 4 bước tuần tự khi có push lên nhánh `main`:
1. **`test`:** Chạy container `python:3.11-slim`, cài dependencies và chạy `pytest tests/ -v` để đảm bảo code pass test trước khi đóng gói.
2. **`build`:** Build Docker image gắn 2 tag `gcr.io/$PROJECT_ID/ai-agent:$COMMIT_SHA` và `:latest`, tận dụng layer cache từ image `:latest` trước đó (`--cache-from`).
3. **`push`:** Đẩy image với các tag vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy`:** Gọi `gcloud run deploy` triển khai image `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình autoscale (`--min-instances=1` tránh cold start, `--max-instances=10`), tài nguyên (`512Mi`, `1` CPU) và gắn secret từ GCP Secret Manager; file `service.yaml` mô tả cấu hình Knative tương đương dưới dạng IaC (kèm `containerConcurrency: 80`, `livenessProbe` `/health` và `startupProbe` `/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

Phân tích `04-api-gateway/develop/app.py`:
- **API key được check ở đâu?** Tại dependency `verify_api_key(api_key: str = Security(api_key_header))` (dòng 39–54), đọc header `X-API-Key` và so sánh với `API_KEY = os.getenv("AGENT_API_KEY", ...)` (dòng 35), inject vào endpoint `POST /ask` qua `Depends(verify_api_key)` (dòng 70).
- **Nếu thiếu hoặc sai key?** Thiếu header trả `401 Unauthorized` (`Missing API key...`); có header nhưng sai giá trị trả `403 Forbidden` (`Invalid API key.`).
- **Làm sao rotate key?** Đổi biến môi trường `AGENT_API_KEY` trên server/nền tảng cloud và restart/rolling-deploy service (trong thực tế có thể hỗ trợ tạm thời cả key cũ + key mới qua danh sách env var để zero-downtime rotation, sau đó gỡ key cũ).

Kết quả test thực tế với `AGENT_API_KEY=secret-key-123` (`curl -i`):

```text
# 1. Không có key -> 401
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# 2. Sai key -> 403
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}

# 3. Đúng key (X-API-Key: secret-key-123) -> 200
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting

**Phân tích `04-api-gateway/production/rate_limiter.py` & `auth.py`:**
- **Algorithm:** **Sliding Window Counter** (dùng `collections.deque` lưu timestamp của từng request trong cửa sổ `window_seconds = 60`; mỗi lần check sẽ `popleft()` các timestamp cũ hơn `now - 60`, kiểm tra `len(window) >= max_requests`).
- **Giới hạn:** `rate_limiter_user` là **10 requests / 60 giây** (tài khoản `student`, role `user`); `rate_limiter_admin` là **100 requests / 60 giây** (tài khoản `teacher`, role `admin`).
- **Xử lý limit cho admin:** Không bypass hoàn toàn mà phân luồng hạn mức theo role trong JWT payload (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user` ở `app.py` dòng 141), giúp admin có quota cao hơn (100 req/min) nhưng vẫn chống được lỗi vòng lặp vô hạn.

**Kết quả test thực tế (`POST /auth/token` với `student` / `demo123`, đã che token):**

```text
# Request 1 (Authorization: Bearer <REDACTED_JWT_TOKEN>) -> 200 OK
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:39:48 GMT
content-length: 184
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}

# Vòng lặp requests 2..13:
Request 2: HTTP 200
Request 3: HTTP 200
Request 4: HTTP 200
Request 5: HTTP 200
Request 6: HTTP 200
Request 7: HTTP 200
Request 8: HTTP 200
Request 9: HTTP 200
Request 10: HTTP 200

# Request 11 -> 429 Too Many Requests
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 09:39:49 GMT
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795599649
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Request 12: HTTP 429
Request 13: HTTP 429
```

---

### Exercise 4.4: Cost guard implementation

- **Cơ chế trong `04-api-gateway/production/cost_guard.py`:**
  1. **Kiểm tra trước khi gọi LLM (`check_budget`):** kiểm tra tổng chi phí toàn hệ thống (`global_daily_budget_usd = $10/ngày`, vượt trả `503`) và chi phí từng user (`daily_budget_usd = $1/ngày`, vượt trả **`402 Payment Required`**); phát log cảnh báo khi dùng đạt 80% budget (`warn_at_pct = 0.8`).
  2. **Ghi nhận sau khi gọi LLM (`record_usage`):** tính tiền theo `PRICE_PER_1K_INPUT_TOKENS` và `PRICE_PER_1K_OUTPUT_TOKENS` rồi cộng dồn vào usage của user và global.
- **Vì sao cần cả Rate Limit lẫn Cost Guard:** Rate limit chỉ bảo vệ **tốc độ** (số request/phút) để tránh nghẽn server; Cost guard bảo vệ **ngân sách tiền LLM** — một user có thể gọi chậm (không chạm rate limit) nhưng gửi prompt rất dài làm tiêu tốn nhiều token và hết ngân sách.
- **Hướng triển khai chuẩn production (dùng cho Part 6):** Thay `_records` in-memory bằng **Redis** (`budget:{user_id}:{YYYY-MM-DD}` hoặc `{YYYY-MM}`), đọc số tiền đã tiêu bằng `GET`, nếu vượt `DAILY_BUDGET_USD`/`MONTHLY_BUDGET_USD` thì trả HTTP `402`; khi gọi thành công thì cộng chi phí bằng `INCRBYFLOAT` và đặt `EXPIRE` tự reset theo chu kỳ ngày/tháng. Nhờ lưu trong Redis, state không bị mất khi restart hay scale nhiều worker.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.2: Health checks & Graceful shutdown (`05-scaling-reliability/develop/app.py`)

1. **Khác biệt giữa Liveness (`/health`) và Readiness (`/ready`):**
   - `GET /health` (**Liveness probe**): Kiểm tra process còn sống không (trả `200` khi app vẫn chạy; trong mẫu kiểm tra thêm trạng thái bộ nhớ). Nếu endpoint này fail, platform sẽ **restart container**.
   - `GET /ready` (**Readiness probe**): Kiểm tra instance đã khởi động xong, chưa bước vào trạng thái shutdown (`_is_ready == True`) và các kết nối phụ thuộc (Redis/DB) đã sẵn sàng chưa. Nếu chưa sẵn sàng, trả **`503`** để load balancer **tạm ngưng route traffic mới** vào instance đó (không restart container).
2. **Cơ chế Graceful Shutdown:**
   - Khi nhận `SIGTERM` (`handle_sigterm` + `uvicorn` với `timeout_graceful_shutdown=30`), uvicorn kích hoạt nhánh shutdown của `lifespan`: đặt `_is_ready = False` để `/ready` trả `503` (ngừng nhận traffic mới), đồng thời chờ `_in_flight_requests` (được đếm qua middleware `track_requests`) xử lý xong hoàn toàn trước khi thoát sạch sẽ.
3. **Kết quả chạy thực tế bản `develop` và gửi `SIGTERM`:**

```text
GET /health -> HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:40:38.447516+00:00","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}

GET /ready -> HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}

POST /ask?question=hello -> HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

# Log khi gửi kill -SIGTERM:
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-25 09:40:41,669 INFO 🔄 Graceful shutdown initiated...
2026-11-25 09:40:41,669 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [2107]
2026-11-25 09:40:41,669 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

---

### Exercise 5.3–5.5: Stateless agent + Load balancing (`05-scaling-reliability/production/`)

1. **Tại sao lưu state trong RAM bị hỏng khi chạy nhiều instance?**
   - Mỗi container/worker có vùng nhớ RAM riêng biệt. Nếu User A gửi request 1 vào `instance-1` (lưu session trong dict của RAM), rồi Nginx round-robin đưa request 2 của User A sang `instance-2`, `instance-2` sẽ không có session đó → mất lịch sử hội thoại / lỗi phiên làm việc.
   - **Giải pháp Stateless:** Toàn bộ session (`session:{session_id}` với TTL 3600s) được lưu tập trung trong **Redis**, nên bất kỳ instance nào nhận request cũng đọc và cập nhật được cùng một cuộc hội thoại.
2. **Kết quả chạy stack 3 replicas + Redis + Nginx (`docker compose -p k5-day14-scaling up -d --build --scale agent=3`) và `python3 test_stateless.py`:**

```text
# Endpoint health & ready qua Nginx (cổng 8080):
GET http://localhost:8080/health -> 200 (X-Served-By: 172.18.0.4:8000, instance-99ee32, storage: redis, redis_connected: true)
GET http://localhost:8080/ready  -> 200 (X-Served-By: 172.18.0.3:8000, instance-79f567)

# Output test_stateless.py:
Session ID: 3c01b821-137e-4971-b4ce-243dca81113a
Request 1: [instance-8cffb6] -> Q: What is Docker?
Request 2: [instance-99ee32] -> Q: Why do we need containers?
Request 3: [instance-79f567] -> Q: What is Kubernetes?
Request 4: [instance-8cffb6] -> Q: How does load balancing work?
Request 5: [instance-99ee32] -> Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-99ee32', 'instance-8cffb6', 'instance-79f567'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10 (5 user + 5 assistant)
✅ Session history preserved across all instances via Redis!
```

*Giải thích:* Nginx phân tán 5 request tuần tự qua cả 3 instance (`instance-8cffb6`, `instance-99ee32`, `instance-79f567`), nhưng khi đọc `GET /chat/{session_id}/history` vẫn thu được trọn vẹn 10 tin nhắn vì mọi instance đều đọc/ghi chung vào Redis.

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `python3 check_production_ready.py` chế độ đầy đủ (có Docker trong WSL2 Ubuntu):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 41/41 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

- Kích thước image Docker build từ `06-lab-complete/Dockerfile`: **273 MB** (`< 500 MB`).
- `docker stop` thoát với **exit code 0** trong **0.8s** (`< 10s`).

---

## AI log

- **CP1 (Part 1):** Hỏi AI hỗ trợ giải thích quy trình CP1 theo checklist K5, chạy kiểm chứng thực tế `01-localhost-vs-production/develop/app.py` và `production/app.py` trong WSL2 Ubuntu, và tổng hợp câu trả lời vào `MISSION_ANSWERS.md`. Đã tự đối chiếu từng số dòng code trong `develop/app.py`, `production/app.py`, `production/config.py` và toàn bộ output `curl` đều lấy trực tiếp từ kết quả chạy thật trên máy.
- **CP2 (Part 2):** Hỏi AI hỗ trợ giải thích kiến trúc multi-stage/Docker Compose, build và chạy kiểm chứng `my-agent:develop`, `my-agent:advanced` và stack Compose (`-p k5-day14-docker`) trong WSL2. Đã tự đối chiếu nội dung `Dockerfile`, `docker-compose.yml`, `nginx.conf` và mọi kích thước image (`1.67 GB` vs `240 MB`, giảm `85.6%`) cùng output `curl` đều lấy trực tiếp từ kết quả đo thật trên máy.
- **CP3 (Part 4):** Hỏi AI hỗ trợ chạy kiểm chứng thực tế API Key auth (`develop`), JWT auth + Rate limiting 10 req/min (`production`, tài khoản `student`/`demo123`) và phân tích Cost Guard. Đã tự kiểm tra logic trong `04-api-gateway/develop/app.py`, `production/auth.py`, `rate_limiter.py`, `cost_guard.py`; toàn bộ mã HTTP (`401`, `403`, `200`, `429`) và header `Retry-After` trong bài đều lấy từ kết quả chạy thật (đã che token).
- **CP4 (Part 5):** Hỏi AI hỗ trợ chạy kiểm chứng `05-scaling-reliability/develop/app.py` (gửi `SIGTERM`) và stack `production` (`-p k5-day14-scaling --scale agent=3` + `test_stateless.py`). Đã tự đối chiếu mã nguồn `develop/app.py`, `production/app.py`, `docker-compose.yml` và ghi nhận kết quả thật (3 instances cùng chia sẻ 10 messages qua Redis).
- **CP5 (Part 6):** Hỏi AI hỗ trợ thiết kế và hoàn thiện TODO trong `06-lab-complete/` (`app/config.py`, `app/redis_client.py`, `app/auth.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`). Sau lần chạy đầu bị lỗi `ModuleNotFoundError: No module named 'uvicorn'` trong container (do `--user` lệch `$HOME=/app` của `appuser`), đã tự chuyển Dockerfile sang `/opt/venv` độc lập và chạy lại `python3 check_production_ready.py` đạt `PASS 12/12` (41/41 checks passed).
- **CP6 (Part 3):** Hỏi AI hỗ trợ cấu hình `06-lab-complete/render.yaml` cho gói Render Free Tier, viết `DEPLOYMENT.md`, kiểm tra các endpoint public (`/health`, `/ready`, `/ask` không key) và đối chiếu `railway.toml` vs `render.yaml` cùng `03-cloud-deployment/production-cloud-run/` (`cloudbuild.yaml`, `service.yaml`). Tự thực hiện tạo Render Key Value (Redis) và Web Service trên Render Dashboard với Public URL `https://k5-l3a-day14-nguyentronghuong.onrender.com`.
- **CP7 (Part 7 Bước 1):** Hỏi AI hỗ trợ chạy chuỗi benchmark `load_test.py` (c=1, 10, 50, 100 và `MOCK_SLOW_RATE=0, 0.03, 0.1`) và `eval/run_eval.py` trên `develop/`, phân tích 2 câu thiếu keyword (`scaling-03`, `security-02`) để bổ sung `KNOWLEDGE_BASE` trong `mock_llm.py`. Đã đối chiếu toàn bộ số liệu trong `BENCHMARK_REPORT.md` mục 1–3 khớp 100% với các file JSON trong `reports/` và kiểm chứng `eval_v2_fixed.json` đạt `100.0% (23/23)` không regression.
- **CP8 (Part 7 Bước 2):** Hỏi AI hỗ trợ chạy `promtool test rules`, bật stack Observability (`-p k5-day14-observability`), sửa lỗi `--user` lệch `$HOME=/app` trong `production/Dockerfile` sang `/opt/venv` để container khởi động được, chạy Locust headless `scale=1` và `scale=3` (với `--no-deps`), truy vấn Jaeger/Prometheus và thực hiện các thí nghiệm chaos A–E. Toàn bộ số liệu trong `BENCHMARK_REPORT.md` mục 4–6 đều lấy trực tiếp từ `scale_1_stats.csv`, `scale_3_stats.csv`, Jaeger API `/api/v3/traces`, Prometheus `/api/v1/alerts` và log JSON của container `agent`.
