# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Nguyễn Trọng Hưởng (MSSV: 2A202603607)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 Ubuntu 26.04.1 LTS (Python 3.14.4), Docker Desktop 29.9.3

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% người dùng nhận phản hồi dưới 0,5 giây (mock LLM base 120ms + jitter 60ms + retrieval 20ms ≈ 180–220ms), giữ trải nghiệm chat mượt mà dù có 3% tail latency ~1,7s |
| Error rate `/ask` | < 2.0 % | Mock LLM mặc định có `MOCK_ERROR_RATE=0.01` (1%); ngưỡng 2% cho phép sai số ngẫu nhiên nhỏ của upstream nhưng vẫn bắt kịp thời nếu lỗi tăng bất thường |
| Accuracy trên golden dataset | ≥ 80 % (sau khi sửa KB: 100 %) | Đảm bảo agent RAG trả lời đúng phần lớn kiến thức cốt lõi và không bị regression khi thay đổi prompt/KB |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.98 | 190.9 | 221.0 | 1694.4 | 2.67% (8/300) | FAIL (error rate > 2.0%) |
| 10 | 36.11 | 189.3 | 225.5 | 1708.5 | 0.67% (2/300) | PASS |
| 50 | 109.32 | 194.1 | 699.4 | 1706.7 | 1.67% (5/300) | FAIL (p95 > 500ms) |
| 100 | 130.87 | 206.6 | 335.7 | 1759.2 | 0.33% (1/300) | PASS |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không tăng tuyến tính ở mức cao: từ c=1 → c=10, RPS tăng gần tuyến tính (~9.1x: `3.98 → 36.11 req/s`) vì agent dùng async I/O (`asyncio.sleep`) nên chưa bão hòa CPU. Từ c=10 → c=50 chỉ tăng ~3.0x (`36.11 → 109.32 req/s`), và từ c=50 → c=100 chỉ tăng thêm ~19.7% (`109.32 → 130.87 req/s`) trong khi p50 tăng dần (`190.9 → 206.6 ms`) do bắt đầu xuất hiện tranh chấp CPU/event loop trên 1 process uvicorn và giới hạn kết nối/bộ đệm I/O; ngoài ra với cỡ mẫu 300 request, chỉ cần hơn 5% request rơi ngẫu nhiên vào nhánh chậm `MOCK_SLOW_RATE=0.03` là p95 nhảy lên (như ở c=50 đạt `699.4 ms`).

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 188.6 | 215.7 | 221.0 |
| 0.03 (mặc định) | 238.1 | 220.5 | 1694.2 |
| 0.1 | 328.3 | 1684.9 | 1705.1 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p99` (và `p95` khi tỉ lệ chậm > 5%) nhạy nhất với request chậm: khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03`, `avg` chỉ tăng nhẹ `+49.5 ms` (`188.6 → 238.1 ms`), nhưng `p99` nhảy vọt **gần 7.7 lần** (`221.0 → 1694.2 ms`). Khi tăng lên `0.1` (10% request bị chậm), `avg` mới là `328.3 ms` (vẫn dưới ngưỡng 500ms!), nhưng `p95` đã vọt lên `1684.9 ms` khiến cứ 20 người dùng thì hơn 1 người phải chờ ~1,7 giây. Vì vậy, **average che giấu nhóm người dùng bị chậm (tail latency)**, nên SLO bắt buộc phải đặt theo percentile (`p95`/`p99`).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.6 | 108.8 | 113.7 |
| Tổng cost (USD) | $0.000397 | $0.000758 | $0.00079 |
| Cost / câu đúng (USD) | $0.00039735 | $0.00003607 | $0.00003436 |
| Quality gate | FAIL | PASS (min 80%) | PASS (min 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) với từ khóa kích hoạt `["kubernetes", "hpa", "autoscaler"]` giải thích HPA scale pod theo CPU, memory và custom metrics (tránh dùng từ khóa `"scale"` để không đụng độ `scaling-01`). |
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry vào `KNOWLEDGE_BASE` với từ khóa kích hoạt `["jwt", "xác thực"]` mô tả JWT là token có thời hạn và chữ ký số (HMAC/RSA) cho xác thực stateless, khác với API key tĩnh. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng vs Chi phí:** v2 dùng retrieval (RAG) đưa context vào prompt nên `avg_tokens` tăng gần gấp đôi (`56.6 → 113.7` tokens/câu) và tổng cost tăng khoảng 2 lần (`$0.000397 → $0.00079`). Tuy nhiên độ chính xác tăng từ **4.3% lên 100.0%**, khiến **chi phí trên mỗi câu trả lời đúng** giảm **~11.6 lần** (`$0.00039735 → $0.00003436`).
- **Latency:** v2 có thêm bước retrieval (~20ms) + prompt dài hơn nhưng p50 chỉ tăng nhẹ (~165ms ở v1 lên ~183ms ở v2), hoàn toàn xứng đáng đổi lấy chất lượng vượt trội.
- **CI Quality Gate:** Khi chạy `python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json`, script phát hiện 20 câu bị regression và thoát với **exit code `1`** (`Quality gate ... ❌ FAIL`). Trong CI (GitHub Actions), chỉ cần chạy bước `python eval/run_eval.py --min-accuracy 0.9 --baseline reports/eval_v2_fixed.json` — nếu exit code ≠ 0, pipeline tự động fail và chặn merge PR vào `main`.

```yaml
# Ví dụ bước Quality Gate trong GitHub Actions (.github/workflows/eval.yml)
- name: Run agent quality gate
  run: |
    AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
    sleep 3
    python eval/run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2.json
```

---

## 4. Observability stack (production)

### 4.1 Screenshot & Đọc dashboard (Exercise 7.4)

- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png`)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png`)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png`)
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

**Đọc số liệu từ Prometheus/Grafana khi chạy tải ổn định (`scale=3`):**
- `req/s` theo từng instance được Nginx chia đều: `13.58`, `13.80`, `13.75` req/s.
- Latency `/ask`: `avg ≈ 239.5 ms`, `p95 ≈ 295.1 ms`, error rate `≈ 1.06%`.
- **Trả lời Exercise 7.4:**
  1. *Khoảng cách giữa `avg` và `p95`/`p99`:* Do `MOCK_SLOW_RATE=0.03` (3% request chậm ~1.7s), nên `avg` (~235 ms) gần `p50` (~190 ms) nhưng `p99` nhảy lên ~1700 ms; nếu tỉ lệ chậm tăng vượt 5% thì `p95` cũng tăng vọt trong khi `avg` chỉ nhích nhẹ.
  2. *Vì sao `input tokens > output tokens` (`3178.7` vs `1674.6` tokens/s):* Ở `AGENT_VERSION=v2`, prompt gửi lên LLM bao gồm `SYSTEM_PROMPT` + tài liệu context lấy từ bước retrieval + câu hỏi người dùng, nên lượng input tokens gần gấp đôi output tokens.
  3. *Vì sao `/metrics` trả `404` khi gọi qua Nginx (`http://localhost:8080/metrics`):* `nginx.conf` có rule `location = /metrics { return 404; }` để chặn truy cập từ bên ngoài, vì `/metrics` lộ thông tin nội bộ (route, lượng traffic, instance, cost); chỉ Prometheus trong mạng nội bộ `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | **+90.0s** (kể từ lúc chạy `up -d` tạo lại container) | Golden Signals: Error rate (đỏ), `req/s` theo status `5xx` |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | **+145.1s** | Golden Signals: p95 latency, Latency & Traffic (`p95`/`p99`) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`, > $2/giờ) | **Firing** (đang active sẵn từ lưu lượng cao + tăng ~16x khi đổi sang `mock-llm-large`) | LLM panel: Cost USD/giờ, LLM p95 latency |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`for: 30s`) | **+40.0s** sau khi `docker pause` | Golden Signals: Instances up giảm, Instances `req/s` mất 1 đường |
| E | `AGENT_VERSION=v1` | Không có alert mới nào liên quan tới chất lượng được kích hoạt | — (không firing vì lỗi chất lượng; `agent_info` đổi sang `v1`) | LLM panel: Retrieval hit ratio mất / về 0, tokens/s giảm, bảng version đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Alert hạ tầng (Prometheus) chỉ đo được **tình trạng sống/chết, latency, HTTP 5xx và chi phí** — không biết câu trả lời của LLM đúng hay sai. Khi chuyển nhầm về `v1`, agent vẫn trả `200 OK` nhanh hơn và rẻ hơn nên toàn bộ metric hạ tầng đều xanh.
- Để phát hiện trong production cần kết hợp: (1) **CI Quality Gate** chạy eval trên golden dataset trước mọi lần deploy (`eval/run_eval.py --baseline ...`), (2) **Online Evaluation / LLM-as-a-judge** chấm mẫu ngẫu nhiên câu trả lời production, và (3) theo dõi **business/RAG metrics** như `retrieval_hit_ratio`, tỉ lệ fallback/không tìm thấy tài liệu, hoặc feedback 👍/👎 của người dùng để đặt alert.
- *(Ghi chú thí nghiệm D):* Lỗi `504 Gateway Timeout` ở Nginx không hiện trên metric của agent vì request bị timeout ở tầng reverse proxy trước khi agent xử lý xong và ghi nhận `http_requests_total`; vì vậy trong production cần giám sát thêm metric/log ở tầng Load Balancer (Nginx/ALB) và synthetic probe từ bên ngoài.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger:

- `trace_id`: `609164997b3f9c37ae1eaf1d8d0643ce`
- Tổng thời gian: **1710.9 ms**
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1692.4 ms**, **98.9%** tổng thời gian; còn `agent.retrieve_context` chỉ mất `16.7 ms` — `1.0%`)
- Dòng log tương ứng (grep theo `trace_id` trong `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-25T10:43:36.030964+00:00", "level": "INFO", "service": "observable-agent", "instance": "9816754f214d", "event": "llm_call", "trace_id": "609164997b3f9c37ae1eaf1d8d0643ce", "span_id": "84a55d1b6359f7ac", "request_id": "86f4d747d9b5", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1692.0}
```

*(Trace lỗi mẫu tìm được trong Jaeger: `trace_id = 050c413d1faf0874db9f41a3a2362eda`, tổng `103.6 ms`, span `chat mock-llm-small` ghi event `exception` và status `ERROR`.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu khớp với `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`:

| Số instance | RPS (Aggregated / `POST /ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures (Aggregated / `POST /ask`) |
|---|---|---|---|---|---|
| 1 | 66.27 / 60.10 | 190 | 230 | 1700 | 61 / 7912 (0.77%) · `/ask`: 61 / 7175 (0.85%) |
| 3 | 66.31 / 60.37 | 190 | 220 | 1700 | 72 / 7915 (0.91%) · `/ask`: 72 / 7205 (1.00%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance gần như **không làm thay đổi RPS (~66.3 req/s) hay p95 (~220–230 ms) / p99 (1700 ms)** vì hai lý do:
1. **Nút thắt mỗi request nằm ở thời gian chờ LLM (`chat mock-llm-small`):** Agent chạy async I/O (`await asyncio.sleep`), phần lớn thời gian (~190 ms bình thường, ~1700 ms khi dính 3% tail latency) là chờ upstream LLM phản hồi chứ không tốn CPU, nên thêm container không làm một lệnh gọi LLM chạy nhanh hơn.
2. **Tải sinh ra từ 100 user Locust còn dưới ngưỡng bão hòa của 1 instance:** Vì mỗi user trong `locustfile.py` nghỉ `0.5–2` giây (`wait_time = between(0.5, 2)`), 100 user chỉ tạo tối đa ~66 req/s — 1 async instance xử lý thoải mái mà chưa bị xếp hàng. Scale lên 3 instance giúp **chia đều tải (~20 req/s mỗi instance)** và tăng **high availability** (1 instance lỗi/restart thì 2 instance kia vẫn gánh tiếp), còn muốn cải thiện `p95`/`p99` thì phải tối ưu phía LLM (streaming, model nhanh hơn, semantic cache, timeout + retry/hedge).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Average đánh lừa cảm nhận người dùng:** SLO hiệu năng phải đo bằng `p95`/`p99` để bắt tail latency, còn benchmark chất lượng không thể bỏ qua **cost trên mỗi câu trả lời đúng** khi chọn kiến trúc (RAG v2 đắt gấp đôi về token nhưng rẻ hơn ~11.6 lần trên mỗi câu đúng).
  2. **3 trụ cột Metrics – Traces – Logs liên kết thành vòng khép kín:** Prometheus/Grafana cảnh báo *khi nào* p95 hoặc error rate tăng → Jaeger chỉ ra *span nào* chậm/lỗi (`chat mock-llm-small` chiếm 98.9%) → `trace_id` giúp grep đúng dòng log JSON chứa chi tiết request/token/cost.
  3. **Metric hạ tầng không thay thế được Eval chất lượng:** Sự cố giảm chất lượng (như chạy nhầm `AGENT_VERSION=v1`) không làm bất kỳ alert hạ tầng nào đỏ, nên bắt buộc phải có **eval quality gate** trong CI/CD trước khi deploy.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Thêm **online quality/RAG metrics** (`retrieval_miss_rate`, độ dài context/similarity score, user feedback rate) và cảnh báo khi retrieval miss tăng vọt.
  - Thêm **Nginx / Load Balancer metrics** (bắt lỗi `502`/`504` mà container agent không tự đếm được) và **Redis / dependency health & rate-limit/cost-guard rejection counters** (`http_429_total`, `http_402_total`) để phát hiện sớm user bị chặn hoặc spam.
