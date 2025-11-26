# Docker Deployment Guide

## Overview

The Binance Bot Docker setup automatically starts the FastAPI service when the container runs. The web GUI and all API endpoints are immediately accessible once the container is up.

## Quick Start

### Using Docker Compose (Recommended)

1. **Start the service**:
   ```bash
   docker compose up -d
   ```

2. **Access the services**:
   - **Log Viewer GUI**: http://localhost:8000/
   - **API Documentation**: http://localhost:8000/docs
   - **Health Check**: http://localhost:8000/health

3. **View logs**:
   ```bash
   docker compose logs -f api
   ```

4. **Stop the service**:
   ```bash
   docker compose down
   ```

### Using Docker Directly

1. **Build the image**:
   ```bash
   docker build -t binance-bot .
   ```

2. **Run the container**:
   ```bash
   docker run -d \
     --name binance-bot \
     --env-file .env \
     -p 8000:8000 \
     binance-bot
   ```

3. **Access the services**:
   - **Log Viewer GUI**: http://localhost:8000/
   - **API Documentation**: http://localhost:8000/docs

## How It Works

### Automatic Service Start

The Dockerfile includes a `CMD` instruction that automatically starts the FastAPI service:

```dockerfile
CMD ["uvicorn", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
```

This means:
- ✅ **No manual command needed** - The service starts automatically when the container runs
- ✅ **Service is always running** - The container keeps the service alive
- ✅ **Web GUI accessible immediately** - Once the container starts, visit http://localhost:8000/

### Port Mapping

The Docker Compose configuration maps port 8000 from the container to your host:

```yaml
ports:
  - "${API_PORT:-8000}:8000"
```

This means:
- The service runs on port 8000 **inside** the container
- Port 8000 on your **host machine** forwards to the container
- Access via `http://localhost:8000` or `http://127.0.0.1:8000`

### Static Files (GUI)

The FastAPI app serves static files from `app/static/`, including the log viewer GUI. The static files are:
- Copied into the Docker image during build
- Served automatically by FastAPI when the container runs
- Accessible at `http://localhost:8000/static/index.html` or just `http://localhost:8000/`

## Docker Compose Services

### API Service

- **Image**: Built from `Dockerfile`
- **Ports**: `8000:8000`
- **Environment**: Loaded from `.env` file
- **Depends on**: Redis service
- **Restart Policy**: `unless-stopped` (auto-restarts on failure)

### Redis Service

- **Image**: `redis:7-alpine`
- **Ports**: `6379:6379`
- **Volumes**: Persistent data storage
- **Restart Policy**: `unless-stopped`

## Production Deployment

For production, use `docker-compose.prod.yml`:

```bash
docker compose -f docker-compose.prod.yml up -d
```

This includes:
- Health checks for both services
- Production-ready configuration
- Automatic restart on failure

## Troubleshooting

### Service Not Accessible

1. **Check if container is running**:
   ```bash
   docker compose ps
   ```

2. **Check container logs**:
   ```bash
   docker compose logs api
   ```

3. **Verify port is not in use**:
   ```bash
   netstat -an | grep 8000  # Linux/Mac
   netstat -an | findstr 8000  # Windows
   ```

### GUI Not Loading

1. **Verify static files are in the image**:
   ```bash
   docker exec binance-bot-api ls -la /app/app/static/
   ```

2. **Check if service is responding**:
   ```bash
   curl http://localhost:8000/health
   ```

3. **Check browser console** for JavaScript errors

### Container Exits Immediately

1. **Check logs for errors**:
   ```bash
   docker compose logs api
   ```

2. **Common issues**:
   - Missing `.env` file
   - Invalid environment variables
   - Port already in use
   - Redis connection issues

### Logs Not Showing in GUI

1. **Verify logs directory exists in container**:
   ```bash
   docker exec binance-bot-api ls -la /app/logs/
   ```

2. **Check file permissions**:
   ```bash
   docker exec binance-bot-api ls -la /app/logs/bot.log
   ```

3. **Create logs directory if missing**:
   ```bash
   docker exec binance-bot-api mkdir -p /app/logs
   ```

## Environment Variables

Ensure your `.env` file contains:

```env
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true
API_PORT=8000
REDIS_URL=redis://redis:6379/0
REDIS_ENABLED=true
```

## Volume Mounting (Optional)

To persist logs outside the container, you can mount a volume:

```yaml
services:
  api:
    volumes:
      - ./logs:/app/logs
```

This ensures logs survive container restarts and can be accessed from the host.

## Security Considerations

- Never commit `.env` files to version control
- Use Docker secrets for sensitive data in production
- Keep Docker images updated
- Use reverse proxy (nginx) in production for HTTPS

