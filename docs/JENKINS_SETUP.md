# Jenkins Setup Guide for Binance Bot

This guide will help you set up Jenkins to run the CI/CD pipeline for the Binance Bot project.

## Prerequisites

Your Jenkins agent (the machine where builds run) needs:
- **Python 3.11 or higher**
- **Docker** (installed and running)
- **Git** (usually pre-installed)
- **Internet connection** (to download dependencies)

## Step-by-Step Setup

### 1. Install Python 3.11+ on Jenkins Agent

#### For Ubuntu/Debian:
```bash
# Update package list
sudo apt update

# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# Verify installation
python3.11 --version

# Make python3 point to Python 3.11 (optional)
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
```

#### For CentOS/RHEL:
```bash
# Install Python 3.11
sudo yum install -y python3.11 python3.11-pip python3.11-devel

# Or use dnf for newer versions
sudo dnf install -y python3.11 python3.11-pip python3.11-devel

# Verify installation
python3.11 --version
```

#### For Jenkins Docker Agent:
If you're using a Docker-based Jenkins agent, use an image with Python pre-installed:
```groovy
agent {
    docker {
        image 'python:3.11-slim'
        args '-v /var/run/docker.sock:/var/run/docker.sock' // For Docker-in-Docker
    }
}
```

### 2. Install Docker on Jenkins Agent

#### For Ubuntu/Debian:
```bash
# Remove old versions
sudo apt remove docker docker-engine docker.io containerd runc

# Install prerequisites
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Verify installation
docker --version
sudo docker run hello-world
```

#### For CentOS/RHEL:
```bash
# Install prerequisites
sudo yum install -y yum-utils

# Add Docker repository
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Install Docker
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Verify installation
docker --version
sudo docker run hello-world
```

### 3. Configure Jenkins User for Docker

The Jenkins user needs permission to use Docker without `sudo`:

```bash
# Add Jenkins user to docker group
sudo usermod -aG docker jenkins

# Or if Jenkins runs as a different user:
sudo usermod -aG docker <jenkins-user>

# Verify (you may need to log out and back in)
groups
# Should show 'docker' in the list

# Test Docker without sudo
docker ps
```

**Important**: After adding the user to the docker group, you may need to:
- Restart the Jenkins service: `sudo systemctl restart jenkins`
- Or log out and log back in

### 4. Install Required Jenkins Plugins

In Jenkins Dashboard → **Manage Jenkins** → **Plugins**:

Install these plugins (if not already installed):
- ✅ **Pipeline** (usually pre-installed)
- ✅ **Git** plugin
- ✅ **GitHub** plugin (for webhooks)
- ✅ **Docker Pipeline** plugin (optional, for Docker agents)
- ✅ **Credentials Binding** plugin (usually pre-installed)

### 5. Configure Jenkins Job

1. **Create New Pipeline Job**:
   - Jenkins Dashboard → **New Item**
   - Name: `binance-bot-pipeline`
   - Type: **Pipeline**
   - Click **OK**

2. **Configure Pipeline**:
   - Scroll to **Pipeline** section
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: `https://github.com/temesgen22/Binance-Bot.git`
   - Credentials: (leave empty for public repo, or add GitHub credentials for private)
   - Branch: `*/main` (or your default branch)
   - Script Path: `Jenkinsfile`
   - Click **Save**

3. **Optional: Configure Environment Variables**:
   - In job configuration → **Build Environment** → **Inject environment variables**
   - Or add in Jenkinsfile environment section
   - Variables:
     - `DOCKER_REGISTRY_URL` (e.g., `registry.hub.docker.com/yourusername`)
     - `DOCKER_REGISTRY_CREDENTIALS_ID` (Jenkins credential ID for Docker registry)

### 6. Test the Pipeline

1. Click **Build Now** on your pipeline job
2. Check the console output for any errors
3. Common issues and fixes:

#### Issue: "python3: not found"
**Solution**: Install Python 3.11+ (see Step 1)

#### Issue: "docker: not found"
**Solution**: Install Docker (see Step 2)

#### Issue: "permission denied" when running Docker
**Solution**: Add Jenkins user to docker group (see Step 3)

#### Issue: "Cannot connect to the Docker daemon"
**Solution**: 
```bash
# Check if Docker is running
sudo systemctl status docker

# Start Docker if not running
sudo systemctl start docker

# Restart Jenkins
sudo systemctl restart jenkins
```

### 7. Set Up GitHub Webhook (Optional)

For automatic builds on push:

1. **In GitHub**:
   - Go to your repository → **Settings** → **Webhooks** → **Add webhook**
   - Payload URL: `http://your-jenkins-url/github-webhook/`
   - Content type: `application/json`
   - Events: **Just the push event**
   - Click **Add webhook**

2. **In Jenkins**:
   - Job configuration → **Build Triggers**
   - Check **GitHub hook trigger for GITScm polling**

## Troubleshooting

### Check Python Installation
```bash
# On Jenkins agent
python3 --version
which python3
```

### Check Docker Installation
```bash
# On Jenkins agent
docker --version
docker info
docker ps
```

### Check Jenkins User Permissions
```bash
# Check if Jenkins user is in docker group
groups jenkins
# Should show: jenkins docker

# Test Docker access
sudo -u jenkins docker ps
```

### View Jenkins Logs
```bash
# On Jenkins server
sudo tail -f /var/log/jenkins/jenkins.log

# Or check Jenkins console output in web UI
```

### Common Error: "No space left on device"
```bash
# Clean up Docker
docker system prune -a

# Clean up Jenkins workspace (if needed)
# In Jenkins: Manage Jenkins → Script Console
# Run: Jenkins.instance.cleanUp()
```

## Alternative: Use Docker Agent

If you can't install Python/Docker on the Jenkins agent, use a Docker-based agent:

Update your `Jenkinsfile`:
```groovy
pipeline {
    agent {
        docker {
            image 'python:3.11-slim'
            args '-v /var/run/docker.sock:/var/run/docker.sock'
        }
    }
    // ... rest of pipeline
}
```

**Note**: This requires Docker-in-Docker setup, which needs additional configuration.

## Verification Checklist

Before running the pipeline, verify:

- [ ] Python 3.11+ installed: `python3 --version`
- [ ] Docker installed: `docker --version`
- [ ] Docker daemon running: `docker ps`
- [ ] Jenkins user in docker group: `groups jenkins`
- [ ] Git installed: `git --version`
- [ ] Internet connectivity from Jenkins agent
- [ ] Jenkins plugins installed (Pipeline, Git, GitHub)
- [ ] Pipeline job configured correctly
- [ ] GitHub repository accessible from Jenkins

## Next Steps

Once the pipeline runs successfully:

1. **Set up automatic deployments** (optional)
2. **Configure Docker registry push** (if needed)
3. **Add notification plugins** (Slack, Email, etc.)
4. **Set up branch protection** in GitHub
5. **Configure deployment environments** (staging, production)

## Support

If you encounter issues:
1. Check Jenkins console output for detailed error messages
2. Verify all prerequisites are installed
3. Check Jenkins logs: `/var/log/jenkins/jenkins.log`
4. Ensure Jenkins user has proper permissions

