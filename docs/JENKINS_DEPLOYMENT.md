# Jenkins Deployment to Cloud Server

This guide explains how to deploy your Binance Bot to a cloud server automatically using Jenkins.

## Overview

The Jenkins pipeline includes a deployment stage that:
1. ✅ Builds and tests your application
2. ✅ Creates a Docker image
3. ✅ Pushes image to registry (optional)
4. ✅ **Deploys to your cloud server via SSH**

## Prerequisites

### On Your Cloud Server:

1. **Docker and Docker Compose installed**
   ```bash
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   
   # Install Docker Compose
   sudo apt-get update
   sudo apt-get install -y docker-compose-plugin
   ```

2. **SSH access configured**
   - SSH server running
   - SSH key-based authentication set up
   - User with Docker permissions

3. **Firewall configured**
   - Port 22 (SSH) open
   - Port 8000 (or your API_PORT) open

### In Jenkins:

1. **SSH Credentials**
   - Create SSH credentials in Jenkins
   - Use SSH username/password or SSH private key

2. **Required Plugins**
   - SSH Pipeline Steps plugin (optional, for advanced scenarios)
   - Or use standard `ssh` command (already available)

## Setup Instructions

### Step 1: Create SSH Credentials in Jenkins

1. Go to **Jenkins Dashboard** → **Manage Jenkins** → **Credentials**
2. Click **Add Credentials**
3. Choose **SSH Username with private key**
4. Fill in:
   - **ID**: `binance-bot-deploy-ssh` (or any name you prefer)
   - **Username**: Your SSH username (e.g., `ubuntu`, `root`, `deploy`)
   - **Private Key**: Paste your SSH private key or upload key file
5. Click **OK**

### Step 2: Configure Jenkins Pipeline Environment Variables

In your Jenkins job configuration:

1. Go to **Pipeline** → **Environment variables** (or use **Build Environment** → **Inject environment variables**)
2. Add these variables:

| Variable | Value | Description |
|----------|-------|-------------|
| `DEPLOY_ENABLED` | `true` | Enable deployment stage |
| `DEPLOY_SSH_CREDENTIALS_ID` | `binance-bot-deploy-ssh` | Your SSH credential ID from Step 1 |
| `DEPLOY_SSH_HOST` | `your-server-ip-or-hostname` | Your cloud server address |
| `DEPLOY_SSH_PORT` | `22` | SSH port (default: 22) |
| `DEPLOY_PATH` | `/opt/binance-bot` | Deployment directory on server |
| `DEPLOY_COMPOSE_FILE` | `docker-compose.yml` | Docker compose file to use |

**Optional (if using Docker registry):**
| Variable | Value | Description |
|----------|-------|-------------|
| `DOCKER_REGISTRY_URL` | `registry.hub.docker.com/username` | Docker registry URL |
| `DOCKER_REGISTRY_CREDENTIALS_ID` | `docker-hub-creds` | Docker registry credentials ID |

### Step 3: Prepare Your Cloud Server

#### Create Deployment Directory

```bash
# SSH into your server
ssh user@your-server-ip

# Create deployment directory
sudo mkdir -p /opt/binance-bot
sudo chown $USER:$USER /opt/binance-bot
cd /opt/binance-bot
```

#### Create docker-compose.yml on Server

```bash
# Copy docker-compose.yml to server (or create manually)
cat > docker-compose.yml << 'EOF'
version: "3.9"

services:
  api:
    image: binance-bot:latest  # Will be updated by Jenkins
    container_name: binance-bot-api
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      REDIS_URL: redis://redis:6379/0
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: binance-bot-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  redis-data:
EOF
```

#### Create .env File

```bash
# Copy .env.example and edit
cp .env.example .env
nano .env  # Edit with your Binance API keys and settings
```

### Step 4: Test Deployment

1. **Run Jenkins Pipeline**
   - Click **Build Now** in your Jenkins job
   - Watch the console output

2. **Verify Deployment**
   ```bash
   # SSH into server
   ssh user@your-server-ip
   
   # Check if containers are running
   cd /opt/binance-bot
   docker-compose ps
   
   # Check logs
   docker-compose logs -f api
   
   # Test API
   curl http://localhost:8000/health
   ```

## Deployment Methods

### Method 1: Direct SSH Deployment (Current Implementation)

**How it works:**
- Jenkins uses SSH to connect to your server
- Copies docker-compose.yml
- Pulls Docker image (if using registry)
- Restarts services with `docker-compose up -d`

**Pros:**
- ✅ Simple setup
- ✅ No registry needed (can use local images)
- ✅ Full control

**Cons:**
- ⚠️ Requires SSH access
- ⚠️ Server must be accessible from Jenkins

### Method 2: Docker Registry + Server Pull

**How it works:**
1. Jenkins pushes image to Docker Hub/Registry
2. Server pulls image from registry
3. Server restarts containers

**Setup:**
- Set `DOCKER_REGISTRY_URL` and `DOCKER_REGISTRY_CREDENTIALS_ID`
- Configure server to pull from registry

**Pros:**
- ✅ Image versioning
- ✅ Can deploy to multiple servers
- ✅ Better for production

### Method 3: Webhook-Based Deployment

**How it works:**
- Jenkins triggers webhook on your server
- Server script handles deployment

**Setup:**
1. Create webhook endpoint on server
2. Configure Jenkins to call webhook after build

## Configuration Examples

### Example 1: Basic Deployment (No Registry)

```groovy
// In Jenkins job environment variables:
DEPLOY_ENABLED = 'true'
DEPLOY_SSH_CREDENTIALS_ID = 'binance-bot-deploy-ssh'
DEPLOY_SSH_HOST = '192.168.1.100'
DEPLOY_SSH_PORT = '22'
DEPLOY_PATH = '/opt/binance-bot'
```

### Example 2: Deployment with Docker Registry

```groovy
// In Jenkins job environment variables:
DEPLOY_ENABLED = 'true'
DEPLOY_SSH_CREDENTIALS_ID = 'binance-bot-deploy-ssh'
DEPLOY_SSH_HOST = 'your-server.com'
DEPLOY_SSH_PORT = '2222'
DEPLOY_PATH = '/opt/binance-bot'
DOCKER_REGISTRY_URL = 'registry.hub.docker.com/yourusername'
DOCKER_REGISTRY_CREDENTIALS_ID = 'docker-hub-creds'
```

### Example 3: Multiple Environments

You can create separate Jenkins jobs for different environments:

**Staging:**
```
DEPLOY_SSH_HOST = 'staging.yourdomain.com'
DEPLOY_PATH = '/opt/binance-bot-staging'
```

**Production:**
```
DEPLOY_SSH_HOST = 'production.yourdomain.com'
DEPLOY_PATH = '/opt/binance-bot-prod'
```

## Security Best Practices

### 1. SSH Key Security

- ✅ Use SSH keys instead of passwords
- ✅ Use dedicated deployment user (not root)
- ✅ Restrict SSH key permissions: `chmod 600 ~/.ssh/id_rsa`
- ✅ Use different keys for different environments

### 2. Server Security

- ✅ Keep Docker and system updated
- ✅ Use firewall (only open necessary ports)
- ✅ Monitor logs regularly
- ✅ Use `.env` file for secrets (never commit to git)

### 3. Jenkins Security

- ✅ Store credentials in Jenkins (never hardcode)
- ✅ Use credential IDs (not actual values)
- ✅ Limit who can trigger deployments
- ✅ Enable build approval for production

## Troubleshooting

### Issue: "Permission denied" on SSH

**Solution:**
```bash
# On server, check SSH key permissions
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# Verify SSH key is in authorized_keys
cat ~/.ssh/authorized_keys
```

### Issue: "Docker command not found" on server

**Solution:**
```bash
# Install Docker on server
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### Issue: "Cannot connect to Docker daemon"

**Solution:**
```bash
# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Check Docker status
sudo systemctl status docker
```

### Issue: Deployment succeeds but service doesn't start

**Check:**
```bash
# On server
cd /opt/binance-bot
docker-compose logs api
docker-compose ps

# Check if .env file exists and is correct
cat .env
```

## Advanced: Blue-Green Deployment

For zero-downtime deployments, you can implement blue-green deployment:

1. Deploy to new containers (green)
2. Test green deployment
3. Switch traffic to green
4. Stop old containers (blue)

This requires additional scripting but provides better uptime.

## Monitoring Deployment

### Check Deployment Status

```bash
# On server
cd /opt/binance-bot
docker-compose ps
docker-compose logs --tail=50 api
```

### Health Check

```bash
# Test API health endpoint
curl http://your-server-ip:8000/health

# Should return:
# {"status":"ok","btc_price":...}
```

## Rollback

If deployment fails, rollback:

```bash
# On server
cd /opt/binance-bot

# Stop current containers
docker-compose down

# Use previous image version
docker-compose up -d binance-bot:previous-version
```

Or configure Jenkins to keep previous images and add a rollback stage.

## Next Steps

1. ✅ Set up SSH credentials in Jenkins
2. ✅ Configure environment variables
3. ✅ Prepare cloud server
4. ✅ Run pipeline and verify deployment
5. ✅ Set up monitoring and alerts
6. ✅ Configure automatic deployments on git push (webhook)

For more details, see the main [README.md](../README.md) and [JENKINS_SETUP.md](JENKINS_SETUP.md).

