# Fix: Docker Permission Denied in Jenkins

## Problem

You're seeing this error:
```
permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock
```

This happens when the Jenkins user inside the container doesn't have permission to access the Docker socket.

## Quick Fix (Windows PowerShell)

Run the provided script:
```powershell
.\fix-jenkins-docker.ps1
```

Or manually:

```powershell
# Stop Jenkins
docker stop jenkins

# Fix permissions
docker exec -u root jenkins bash -c "groupadd -f docker && usermod -aG docker jenkins && chmod 666 /var/run/docker.sock"

# Start Jenkins
docker start jenkins

# Test
docker exec -u jenkins jenkins docker ps
```

## Permanent Solution

### Option 1: Use docker-compose (Recommended)

Use the provided `docker-compose.jenkins.yml`:

```bash
# Stop and remove existing Jenkins
docker stop jenkins
docker rm jenkins

# Start with docker-compose (handles permissions automatically)
docker-compose -f docker-compose.jenkins.yml up -d
```

### Option 2: Recreate Container with Root User

If permissions still don't work, run Jenkins as root (less secure but simpler):

```bash
docker stop jenkins
docker rm jenkins

docker run -d \
  --name jenkins \
  --user root \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  jenkins/jenkins:lts bash -c "
    apt-get update && 
    apt-get install -y docker.io && 
    su jenkins -c '/usr/local/bin/jenkins.sh'
  "
```

**Note**: Running as root is less secure. For production, use Option 1.

### Option 3: Match GID (Linux only)

On Linux, match the docker group GID:

```bash
# Get docker group GID from host
DOCKER_GID=$(getent group docker | cut -d: -f3)

# Recreate Jenkins with matching GID
docker run -d \
  --name jenkins \
  --user root \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  jenkins/jenkins:lts bash -c "
    groupadd -g $DOCKER_GID docker && 
    usermod -aG docker jenkins && 
    apt-get update && 
    apt-get install -y docker.io && 
    su jenkins -c '/usr/local/bin/jenkins.sh'
  "
```

## Verification

After applying the fix, test Docker access:

```bash
# Test as Jenkins user
docker exec -u jenkins jenkins docker info
docker exec -u jenkins jenkins docker ps

# Should work without errors
```

## Why This Happens

On Windows with Docker Desktop:
- Docker socket permissions are managed differently
- The Jenkins user (UID 1000) may not match the docker group
- Socket permissions may need to be adjusted

## Security Note

Changing socket permissions to `666` (readable/writable by all) is less secure but often necessary for Docker-in-Docker scenarios. For production:
- Use a dedicated Docker daemon for CI/CD
- Or use Docker-in-Docker (DinD) with proper isolation
- Or use Kubernetes with proper service accounts

## Still Having Issues?

1. **Check Docker socket permissions on host**:
   ```bash
   # On Linux
   ls -la /var/run/docker.sock
   
   # Should show: srw-rw---- 1 root docker
   ```

2. **Check Jenkins user groups**:
   ```bash
   docker exec jenkins groups jenkins
   # Should include 'docker'
   ```

3. **Check Docker daemon is running**:
   ```bash
   docker ps  # On host, should work
   ```

4. **Try running as root** (temporary test):
   ```bash
   docker exec -u root jenkins docker ps
   # If this works, it's a permissions issue
   ```

For more help, see [JENKINS_DOCKER_IN_DOCKER.md](JENKINS_DOCKER_IN_DOCKER.md)

