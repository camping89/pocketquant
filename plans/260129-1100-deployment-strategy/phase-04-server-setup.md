# Phase 04: Vultr Server Setup

## Context

- **Parent:** [plan.md](plan.md)
- **Dependencies:** None (can run parallel with Phase 01-03)
- **Docs:** Vultr documentation

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 |
| Status | ⏳ Pending |
| Effort | 45m |

Provision fresh Ubuntu 22.04 VPS với Docker và security hardening.

## Key Insights

- Fresh Ubuntu 22.04 LTS
- 2GB RAM sufficient for stack
- Security: SSH key only, UFW, non-root user
- Docker via official script

## Requirements

### Functional
- Docker và Docker Compose installed
- Non-root deploy user với docker access
- SSH key authentication
- App directory với proper permissions

### Non-functional
- SSH port 22 only from your IP (optional)
- Firewall: 22, 8000 only
- Fail2ban for SSH protection

## Architecture

```
┌─────────────────────────────────────────┐
│           Vultr VPS (2GB RAM)           │
│                                          │
│  User: deploy (uid 1000)                │
│  Docker: /var/run/docker.sock           │
│  App: /opt/pocketquant                  │
│                                          │
│  UFW: 22 ✓  8000 ✓  * ✗                │
└─────────────────────────────────────────┘
```

## Related Code Files

### Files to Create
- `scripts/server-setup.sh`

## Implementation Steps

### Step 1: Initial Server Access

```bash
# SSH as root (first time)
ssh root@<vultr-ip>

# Update system
apt update && apt upgrade -y
```

### Step 2: Create Deploy User

```bash
# Create user
adduser deploy --disabled-password --gecos ""

# Add to sudo group
usermod -aG sudo deploy

# Setup SSH key for deploy user
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh

# Add your public key
echo "ssh-ed25519 AAAA... your-email@example.com" > /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
```

### Step 3: Install Docker

```bash
# Official Docker installation
curl -fsSL https://get.docker.com | sh

# Add deploy user to docker group
usermod -aG docker deploy

# Enable Docker service
systemctl enable docker
systemctl start docker
```

### Step 4: Configure Firewall

```bash
# Install UFW if not present
apt install -y ufw

# Default deny incoming
ufw default deny incoming
ufw default allow outgoing

# Allow SSH
ufw allow 22/tcp

# Allow API
ufw allow 8000/tcp

# Enable firewall
ufw enable

# Verify
ufw status
```

### Step 5: Disable Password Authentication

```bash
# Edit SSH config
nano /etc/ssh/sshd_config

# Set these values:
# PasswordAuthentication no
# PubkeyAuthentication yes
# PermitRootLogin no

# Restart SSH
systemctl restart sshd
```

### Step 6: Install Fail2ban

```bash
apt install -y fail2ban

# Create config
cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF

systemctl enable fail2ban
systemctl restart fail2ban
```

### Step 7: Create App Directory

```bash
# Create directory
mkdir -p /opt/pocketquant/docker

# Set ownership
chown -R deploy:deploy /opt/pocketquant

# Clone compose files (as deploy user)
su - deploy
cd /opt/pocketquant
git clone --depth 1 https://github.com/<user>/pocketquant.git .
# Or just copy docker/ folder manually
```

### Step 8: Create server-setup.sh Script

```bash
#!/bin/bash
# scripts/server-setup.sh
# Run as root on fresh Ubuntu 22.04

set -e

echo "=== PocketQuant Server Setup ==="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root${NC}"
  exit 1
fi

# Get public key from user
read -p "Enter your SSH public key: " SSH_PUBLIC_KEY

echo "=== Updating system ==="
apt update && apt upgrade -y

echo "=== Installing dependencies ==="
apt install -y curl git ufw fail2ban

echo "=== Creating deploy user ==="
if id "deploy" &>/dev/null; then
    echo "User deploy already exists"
else
    adduser deploy --disabled-password --gecos ""
    usermod -aG sudo deploy
fi

echo "=== Setting up SSH key ==="
mkdir -p /home/deploy/.ssh
echo "$SSH_PUBLIC_KEY" > /home/deploy/.ssh/authorized_keys
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

echo "=== Installing Docker ==="
if command -v docker &> /dev/null; then
    echo "Docker already installed"
else
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker deploy
systemctl enable docker

echo "=== Configuring firewall ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 8000/tcp
echo "y" | ufw enable

echo "=== Configuring SSH ==="
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

echo "=== Configuring Fail2ban ==="
cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF
systemctl enable fail2ban
systemctl restart fail2ban

echo "=== Creating app directory ==="
mkdir -p /opt/pocketquant/docker
chown -R deploy:deploy /opt/pocketquant

echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Test SSH: ssh deploy@$(hostname -I | awk '{print $1}')"
echo "2. Copy docker/compose.prod.yml to /opt/pocketquant/docker/"
echo "3. Create /opt/pocketquant/docker/.env.prod with secrets"
echo "4. Run: docker compose -f docker/compose.prod.yml up -d"
```

### Step 9: Verify Setup

```bash
# Test SSH as deploy user
ssh deploy@<vultr-ip>

# Verify docker access
docker ps

# Check firewall
sudo ufw status

# Check fail2ban
sudo fail2ban-client status sshd
```

## Todo List

- [ ] Create `scripts/server-setup.sh`
- [ ] SSH to Vultr as root
- [ ] Run setup script
- [ ] Verify SSH as deploy user
- [ ] Verify docker works
- [ ] Verify firewall rules

## Success Criteria

- [ ] Can SSH as `deploy` user
- [ ] Cannot SSH as `root`
- [ ] `docker ps` works as deploy
- [ ] UFW shows only 22, 8000 open
- [ ] Fail2ban active

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Locked out of SSH | Critical | Keep root session open during setup |
| Firewall blocks SSH | Critical | Set SSH rule before enable |
| Docker permission denied | Medium | Logout/login after usermod |

## Security Considerations

- No root SSH login
- Password auth disabled
- Fail2ban protects against brute force
- Minimal ports exposed
- Non-root user for app

## Next Steps

After completion → [Phase 05: Monitoring](phase-05-monitoring.md)
