# WOOHWAHAE E-commerce Backend Deployment Guide

## Quick Start (Development)

```bash
# 1. Navigate to project
cd /Users/97layer/97layerOS/core/backend/ecommerce

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Edit .env with your configuration

# 5. Start PostgreSQL
# macOS:
brew services start postgresql
createdb woohwahae_ecommerce

# Docker:
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=woohwahae_ecommerce \
  -p 5432:5432 \
  postgres:15

# 6. Start Redis
# macOS:
brew services start redis

# Docker:
docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:7-alpine

# 7. Initialize database
python migrations/init_db.py

# 8. Run development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API available at:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

Default admin credentials:
- Email: `admin@woohwahae.kr`
- Password: `changeme123`

⚠️ **Change password immediately in production!**

---

## Production Deployment on VM (136.109.201.201)

### 1. VM Setup

```bash
# SSH into VM
ssh 97layer-vm

# Create app directory
sudo mkdir -p /opt/woohwahae-ecommerce
sudo chown $USER:$USER /opt/woohwahae-ecommerce
cd /opt/woohwahae-ecommerce

# Clone repository (or sync files)
git clone https://github.com/yourusername/97layerOS.git .
cd core/backend/ecommerce
```

### 2. Install Dependencies

```bash
# Install Python 3.11+ if not available
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn
```

### 3. PostgreSQL Setup

```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
```

```sql
CREATE DATABASE woohwahae_ecommerce;
CREATE USER woohwahae WITH PASSWORD 'secure-password-here';
GRANT ALL PRIVILEGES ON DATABASE woohwahae_ecommerce TO woohwahae;
\q
```

### 4. Redis Setup

```bash
# Install Redis
sudo apt install redis-server

# Configure Redis
sudo nano /etc/redis/redis.conf
# Set: supervised systemd

# Start Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### 5. Environment Configuration

```bash
# Create production .env
nano .env
```

```env
DATABASE_URL=postgresql://woohwahae:secure-password-here@localhost:5432/woohwahae_ecommerce
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

JWT_SECRET_KEY=generate-long-random-secret-key-here
JWT_EXPIRE_MINUTES=10080

STRIPE_API_KEY=sk_live_your_stripe_key_here
TOSSPAYMENTS_SECRET_KEY=live_sk_your_tosspayments_secret_key_here
TOSSPAYMENTS_CLIENT_KEY=live_ck_your_tosspayments_client_key_here

DEBUG=False
```

Generate secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 6. Initialize Database

```bash
source venv/bin/activate
python migrations/init_db.py
```

### 7. Systemd Service

Create service file:
```bash
sudo nano /etc/systemd/system/woohwahae-ecommerce.service
```

```ini
[Unit]
Description=WOOHWAHAE E-commerce API
After=network.target postgresql.service redis-server.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/woohwahae-ecommerce/core/backend/ecommerce
Environment="PATH=/opt/woohwahae-ecommerce/core/backend/ecommerce/venv/bin"
ExecStart=/opt/woohwahae-ecommerce/core/backend/ecommerce/venv/bin/gunicorn \
    main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8001 \
    --access-logfile /var/log/woohwahae-ecommerce/access.log \
    --error-logfile /var/log/woohwahae-ecommerce/error.log \
    --log-level info
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Create log directory:
```bash
sudo mkdir -p /var/log/woohwahae-ecommerce
sudo chown www-data:www-data /var/log/woohwahae-ecommerce
```

Enable and start service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable woohwahae-ecommerce
sudo systemctl start woohwahae-ecommerce
sudo systemctl status woohwahae-ecommerce
```

### 8. Nginx Configuration

Add to existing nginx config:
```bash
sudo nano /etc/nginx/sites-available/woohwahae
```

```nginx
# E-commerce API upstream
upstream ecommerce_api {
    server 127.0.0.1:8001;
}

# Add to server block for api.woohwahae.kr
server {
    listen 443 ssl http2;
    server_name api.woohwahae.kr;

    # Existing SSL configuration...

    # E-commerce API endpoints
    location /api/v1 {
        proxy_pass http://ecommerce_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CORS headers (if not handled by FastAPI)
        add_header Access-Control-Allow-Origin "https://woohwahae.kr" always;
        add_header Access-Control-Allow-Methods "GET, POST, PATCH, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Session-ID" always;
        add_header Access-Control-Allow-Credentials "true" always;

        if ($request_method = 'OPTIONS') {
            return 204;
        }
    }

    # Health check endpoint
    location /health {
        proxy_pass http://ecommerce_api;
        access_log off;
    }

    # Existing configurations...
}
```

Test and reload nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 9. Deployment Script

Create deployment script:
```bash
nano /opt/woohwahae-ecommerce/deploy-ecommerce.sh
```

```bash
#!/bin/bash
set -e

echo "🚀 Deploying WOOHWAHAE E-commerce API..."

# Navigate to project
cd /opt/woohwahae-ecommerce

# Pull latest code
echo "📥 Pulling latest code..."
git fetch origin main
git reset --hard origin/main

# Activate virtual environment
source core/backend/ecommerce/venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
cd core/backend/ecommerce
pip install -r requirements.txt --quiet

# Run database migrations (if using Alembic)
# echo "🔄 Running migrations..."
# alembic upgrade head

# Restart service
echo "🔄 Restarting service..."
sudo systemctl restart woohwahae-ecommerce

# Check status
sleep 2
if systemctl is-active --quiet woohwahae-ecommerce; then
    echo "✅ Deployment successful!"
    echo "📊 Service status:"
    systemctl status woohwahae-ecommerce --no-pager -l
else
    echo "❌ Deployment failed!"
    echo "📋 Service logs:"
    sudo journalctl -u woohwahae-ecommerce -n 50 --no-pager
    exit 1
fi
```

Make executable:
```bash
chmod +x /opt/woohwahae-ecommerce/deploy-ecommerce.sh
```

### 10. Integration with Existing Deploy Script

Add to `/Users/97layer/97layerOS/deploy.sh`:

```bash
# E-commerce backend deployment
deploy_ecommerce() {
    log "Deploying e-commerce backend..."
    ssh 97layer-vm "bash /opt/woohwahae-ecommerce/deploy-ecommerce.sh"
}

# Add to deploy_all function
deploy_all() {
    # ... existing deployments ...
    deploy_ecommerce
}
```

---

## Monitoring & Maintenance

### Check Service Status

```bash
# Service status
sudo systemctl status woohwahae-ecommerce

# Live logs
sudo journalctl -u woohwahae-ecommerce -f

# Access logs
sudo tail -f /var/log/woohwahae-ecommerce/access.log

# Error logs
sudo tail -f /var/log/woohwahae-ecommerce/error.log
```

### Database Backup

```bash
# Manual backup
pg_dump -U woohwahae woohwahae_ecommerce > backup_$(date +%Y%m%d_%H%M%S).sql

# Automated daily backup (crontab)
0 2 * * * pg_dump -U woohwahae woohwahae_ecommerce | gzip > /backups/ecommerce_$(date +\%Y\%m\%d).sql.gz
```

### Redis Backup

```bash
# Manual backup
redis-cli SAVE

# Backup file location
sudo cp /var/lib/redis/dump.rdb /backups/redis_$(date +%Y%m%d).rdb
```

### Health Monitoring

Add to monitoring script:

```bash
# Check API health
curl -f https://api.woohwahae.kr/health || alert "E-commerce API down"

# Check database connection
PGPASSWORD=password psql -U woohwahae -d woohwahae_ecommerce -c "SELECT 1" || alert "Database down"

# Check Redis
redis-cli ping || alert "Redis down"
```

---

## Security Checklist

- [ ] Change default admin password
- [ ] Use strong JWT secret key (64+ characters)
- [ ] Enable HTTPS only (no HTTP)
- [ ] Restrict CORS origins to production domains
- [ ] Set proper PostgreSQL user permissions
- [ ] Enable Redis password protection (if exposed)
- [ ] Configure firewall (UFW) to only allow 80/443
- [ ] Set up fail2ban for brute force protection
- [ ] Regular database backups
- [ ] Monitor logs for suspicious activity
- [ ] Keep dependencies updated
- [ ] Use environment variables for all secrets

---

## Performance Tuning

### Gunicorn Workers

Calculate optimal workers:
```bash
# Formula: (2 x CPU cores) + 1
nproc  # Get CPU count
# Example: 4 cores = 9 workers
```

Update service file:
```
--workers 9
```

### Database Connection Pool

Update `models/base.py`:
```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True
)
```

### Redis Optimization

Edit `/etc/redis/redis.conf`:
```
maxmemory 256mb
maxmemory-policy allkeys-lru
```

---

## Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u woohwahae-ecommerce -n 100 --no-pager

# Common issues:
# 1. Database connection failed
#    → Check DATABASE_URL in .env
#    → Verify PostgreSQL is running

# 2. Redis connection failed
#    → Verify Redis is running
#    → Check REDIS_HOST/PORT in .env

# 3. Port already in use
#    → Check for processes on port 8001
#    → Change bind address in service file
```

### Database migration issues

```bash
# Reset database (DANGER: deletes all data)
dropdb woohwahae_ecommerce
createdb woohwahae_ecommerce
python migrations/init_db.py
```

### Performance issues

```bash
# Check database slow queries
sudo tail -f /var/log/postgresql/postgresql-15-main.log

# Check API response times
sudo tail -f /var/log/woohwahae-ecommerce/access.log

# Monitor system resources
htop
```

---

## Next Steps After Deployment

1. **Frontend Integration**
   - Implement API client in website/
   - Add product catalog pages
   - Build shopping cart UI
   - Create checkout flow

2. **Payment Integration**
   - Complete Stripe/TossPayments implementation
   - Set up webhook endpoints
   - Test payment flows

3. **Email Notifications**
   - Order confirmation emails
   - Shipping notifications
   - Password reset

4. **Admin Dashboard**
   - Product management UI
   - Order management UI
   - Customer management
   - Analytics dashboard

5. **Additional Features**
   - Product reviews
   - Wishlist
   - Discount codes
   - Inventory alerts
   - Order tracking
