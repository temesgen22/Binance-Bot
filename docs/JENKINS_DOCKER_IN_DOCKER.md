# Fix: Docker Command Not Found in Jenkins Container

## Problem

When you exec into your Jenkins container, Docker commands don't work:
```bash
docker exec -it jenkins bash
# Inside container:
docker ps
# Error: docker: command not found
```

This happens because Jenkins is running in a Docker container, but Docker CLI is not installed inside the container.

## Solution Options

### Option 1: Use Docker Socket Mounting (Recommended)

Mount the host's Docker socket into the Jenkins container. This allows Jenkins to use the host's Docker daemon.

#### If using docker-compose:

Create or update `docker-compose.jenkins.yml`:

```yaml
version: '3.8'

services:
  jenkins:
    image: jenkins/jenkins:lts
    container_name: jenkins
    user: root  # Required to access Docker socket
    ports:
      - "8080:8080"
      - "50000:50000"
    volumes:
      - jenkins_home:/var/jenkins_home
      # Mount Docker socket from host
      - /var/run/docker.sock:/var/run/docker.sock
      # Mount Docker binary from host
      - /usr/bin/docker:/usr/bin/docker:ro
    environment:
      - DOCKER_HOST=unix:///var/run/docker.sock
    restart: unless-stopped

volumes:
  jenkins_home:
```

**Start Jenkins:**
```bash
docker-compose -f docker-compose.jenkins.yml up -d
```

#### If using docker run:

```bash
# Stop existing Jenkins
docker stop jenkins
docker rm jenkins

# Start Jenkins with Docker socket mounted
docker run -d \
  --name jenkins \
  --user root \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /usr/bin/docker:/usr/bin/docker:ro \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  jenkins/jenkins:lts
```

### Option 2: Install Docker CLI in Jenkins Container

Build a custom Jenkins image with Docker CLI installed.

**Build the custom image:**
```bash
docker build -f Dockerfile.jenkins -t jenkins-with-docker:lts .
```

**Run Jenkins with the custom image:**
```bash
docker run -d \
  --name jenkins \
  --user root \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  jenkins-with-docker:lts
```

### Option 3: Install Docker CLI in Running Container

If Jenkins is already running, you can install Docker CLI inside it:

```bash
# Exec into Jenkins container as root
docker exec -it -u root jenkins bash

# Inside container, install Docker CLI
apt-get update
apt-get install -y docker.io

# Add Jenkins user to docker group
groupadd -f docker
usermod -aG docker jenkins

# Exit and restart Jenkins container
exit
docker restart jenkins
```

**Note**: This change will be lost if you recreate the container. Use Option 1 or 2 for a permanent solution.

## Verification

After applying the fix, verify Docker works:

```bash
# Exec into Jenkins container
docker exec -it jenkins bash

# Inside container, test Docker
docker ps
docker --version
docker info

# Should work without errors
```

## Important Notes

### Security Considerations

Mounting the Docker socket gives the Jenkins container full access to the host's Docker daemon. This is a security consideration:

- **Only do this on trusted systems**
- **Consider using Docker-in-Docker (DinD) for production** (more complex setup)
- **Or use a separate Docker daemon** for Jenkins builds

### Permission Issues

If you get permission errors:

```bash
# On the host, check Docker socket permissions
ls -la /var/run/docker.sock
# Should show: srw-rw---- 1 root docker

# Fix permissions if needed
sudo chmod 666 /var/run/docker.sock

# Or add jenkins user to docker group (if Jenkins runs as different user)
sudo usermod -aG docker <jenkins-user>
```

### Jenkins User

The Jenkins container runs as user `jenkins` by default. To access Docker socket, you may need to:

1. Run container as `root` (simpler but less secure)
2. Or ensure `jenkins` user is in `docker` group inside container

## Quick Fix Script

Run this script to fix your existing Jenkins container:

```bash
#!/bin/bash
# fix-jenkins-docker.sh

echo "Stopping Jenkins..."
docker stop jenkins

echo "Installing Docker CLI in Jenkins container..."
docker exec -u root jenkins bash -c "
    apt-get update && 
    apt-get install -y docker.io && 
    groupadd -f docker && 
    usermod -aG docker jenkins
"

echo "Restarting Jenkins..."
docker start jenkins

echo "Verifying Docker access..."
sleep 5
docker exec jenkins docker ps

echo "Done! Docker should now work in Jenkins container."
```

## Troubleshooting

### Issue: "Cannot connect to Docker daemon"

**Solution**: Ensure Docker socket is mounted:
```bash
docker exec jenkins ls -la /var/run/docker.sock
# Should show the socket file
```

### Issue: "Permission denied"

**Solution**: Run container as root or fix permissions:
```bash
docker run --user root ...
```

### Issue: "docker: command not found" after restart

**Solution**: Use Option 1 or 2 (persistent solutions) instead of Option 3.

## Recommended Setup

For production, I recommend **Option 1** (Docker socket mounting) because:
- ✅ Simple to set up
- ✅ Uses host's Docker daemon (efficient)
- ✅ No need to maintain custom images
- ✅ Works with docker-compose

Use the provided `docker-compose.jenkins.yml` file for the easiest setup.

