# Deployment Information

## Public URL
https://k5-l3a-day14-nguyentronghuong.onrender.com

## Platform
Render (Free Tier Web Service + Render Key Value / Redis Free)

## Test Commands

### Health & Readiness Checks
```bash
curl https://k5-l3a-day14-nguyentronghuong.onrender.com/health
# Expected: {"status":"ok","environment":"production","uptime_seconds":...}

curl https://k5-l3a-day14-nguyentronghuong.onrender.com/ready
# Expected: {"ready":true}
```

### API Test (Authentication & Inference)
```bash
# Missing API key -> 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://k5-l3a-day14-nguyentronghuong.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# Valid API key -> 200
curl -X POST https://k5-l3a-day14-nguyentronghuong.onrender.com/ask \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set
- `PORT` (injected automatically by Render)
- `ENVIRONMENT=production`
- `REDIS_URL` (Internal Render Key Value URL)
- `AGENT_API_KEY` (configured on Render Dashboard, not committed)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
