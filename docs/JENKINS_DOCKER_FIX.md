# Fix: Docker Daemon Not Running in Jenkins

## Problem

You're seeing this error in Jenkins:
```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock. 
Is the docker daemon running?
```

## Solution

### Option 1: Start Docker Service (Recommended)

If Jenkins is running on a Linux server/VM:

```bash
# SSH into your Jenkins agent/server
ssh user@your-jenkins-server

# Start Docker service
sudo systemctl start docker

# Enable Docker to start on boot (optional but recommended)
sudo systemctl enable docker

# Verify Docker is running
sudo docker ps

# Restart Jenkins (if needed)
sudo systemctl restart jenkins
```

### Option 2: Jenkins Running in Docker Container

If Jenkins itself is running in a Docker container, you need to mount the Docker socket:

**Stop your Jenkins container:**
```bash
docker stop jenkins
```

**Start Jenkins with Docker socket mounted:**
```bash
docker run -d \
  --name jenkins \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /usr/bin/docker:/usr/bin/docker \
  jenkins/jenkins:lts
```

**Or update your docker-compose.yml:**
```yaml
services:
  jenkins:
    image: jenkins/jenkins:lts
    volumes:
      - jenkins_home:/var/jenkins_home
      - /var/run/docker.sock:/var/run/docker.sock
      - /usr/bin/docker:/usr/bin/docker
    ports:
      - "8080:8080"
      - "50000:50000"
```

### Option 3: Jenkins User Permissions

If Docker is running but Jenkins user can't access it:

```bash
# Add Jenkins user to docker group
sudo usermod -aG docker jenkins

# If Jenkins runs as different user, replace 'jenkins' with that user
# Check Jenkins user: ps aux | grep jenkins

# Restart Jenkins
sudo systemctl restart jenkins

# Or if Jenkins is in Docker:
docker restart jenkins
```

### Option 4: Verify Docker Installation

Check if Docker is properly installed:

```bash
# Check Docker version
docker --version

# Check Docker service status
sudo systemctl status docker

# Check Docker socket
ls -la /var/run/docker.sock

# Should show: srw-rw---- 1 root docker
```

If the socket doesn't exist or has wrong permissions:

```bash
# Fix socket permissions
sudo chmod 666 /var/run/docker.sock

# Or better: add user to docker group (see Option 3)
```

## Quick Diagnostic Commands

Run these on your Jenkins agent to diagnose:

```bash
# 1. Check if Docker is installed
which docker
docker --version

# 2. Check if Docker daemon is running
sudo systemctl status docker

# 3. Check Docker socket
ls -la /var/run/docker.sock

# 4. Test Docker access (as Jenkins user)
sudo -u jenkins docker ps

# 5. Check Jenkins user groups
groups jenkins
# Should include 'docker'
```

## Common Issues

### Issue: "permission denied" when running docker
**Solution**: Add Jenkins user to docker group (Option 3)

### Issue: Docker service won't start
**Solution**: 
```bash
# Check Docker logs
sudo journalctl -u docker.service

# Reinstall Docker if needed (see JENKINS_SETUP.md)
```

### Issue: Jenkins in Docker can't access host Docker
**Solution**: Mount Docker socket (Option 2)

### Issue: Docker socket doesn't exist
**Solution**: Start Docker service (Option 1)

## Verification

After fixing, verify in Jenkins:

1. Run the pipeline again
2. Check the "Check Prerequisites" stage
3. Should see: `✓ Docker found and running`

Or test manually on Jenkins agent:
```bash
docker info
docker ps
```

Both commands should work without errors.

## Still Having Issues?

1. **Check Jenkins logs**: `/var/log/jenkins/jenkins.log` or `docker logs jenkins`
2. **Check Docker logs**: `sudo journalctl -u docker.service`
3. **Verify network**: Ensure Jenkins agent can reach Docker daemon
4. **Check SELinux/AppArmor**: May block Docker socket access

For more details, see [JENKINS_SETUP.md](JENKINS_SETUP.md)

