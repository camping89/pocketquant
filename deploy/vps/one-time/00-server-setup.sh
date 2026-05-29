#!/bin/bash
# Server provisioning script for PocketQuant
# Run ONCE as root on fresh Ubuntu 22.04 VPS
#
# WHY THIS SCRIPT RUNS MANUALLY (NOT IN CI/CD):
# - All steps require root privileges
# - CI/CD uses 'deploy' user which has no sudo (passwordless for security)
# - Docker group membership only takes effect after logout/login (not same session)
# - This is a chicken-egg problem: CI/CD needs 'deploy' user to exist first
#
# WHAT THIS SCRIPT DOES:
# 1. Install Docker          - needs root
# 2. Create 'deploy' user    - needs root
# 3. Add to docker group     - needs root, effect after re-login
# 4. Setup SSH keys          - needs root to write to other user's home
# 5. Configure firewall      - needs root
# 6. Harden SSH              - needs root
# 7. Setup Fail2ban          - needs root
# 8. Create app directory    - needs root to chown

set -e

echo "=== PocketQuant Server Setup ==="

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root${NC}"
  exit 1
fi

read -p "Enter your SSH public key: " SSH_PUBLIC_KEY

# Ports (customize if needed)
SSH_PORT=${SSH_PORT:-49722}
HTTP_PORT=${HTTP_PORT:-51080}
HTTPS_PORT=${HTTPS_PORT:-51443}

echo "=== Updating system ==="
apt update && apt upgrade -y
apt install -y curl ufw fail2ban

echo "=== Installing Docker ==="
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
else
    echo "Docker already installed: $(docker --version)"
fi

echo "=== Creating deploy user ==="
if id "deploy" &>/dev/null; then
    echo "User deploy already exists"
else
    adduser deploy --disabled-password --gecos ""
fi

# Add deploy user to docker group (allows running docker without sudo)
usermod -aG docker deploy

echo "=== Setting up SSH key ==="
mkdir -p /home/deploy/.ssh
echo "$SSH_PUBLIC_KEY" > /home/deploy/.ssh/authorized_keys
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

echo "=== Configuring firewall ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow ${SSH_PORT}/tcp
ufw allow ${HTTP_PORT}/tcp
ufw allow ${HTTPS_PORT}/tcp
echo "y" | ufw enable

echo "=== Hardening SSH ==="
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i "s/#Port 22/Port ${SSH_PORT}/" /etc/ssh/sshd_config
sed -i "s/Port 22/Port ${SSH_PORT}/" /etc/ssh/sshd_config
systemctl restart sshd

echo "=== Configuring Fail2ban ==="
cat > /etc/fail2ban/jail.local << EOF
[sshd]
enabled = true
port = ${SSH_PORT}
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF
systemctl enable fail2ban
systemctl restart fail2ban

echo "=== Creating app directory ==="
mkdir -p /opt/pocketquant/deploy/vps/one-time
chown -R deploy:deploy /opt/pocketquant

echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Ports: SSH=${SSH_PORT}, HTTP=${HTTP_PORT}, HTTPS=${HTTPS_PORT}"
echo ""
echo "Next steps:"
echo "1. Test SSH: ssh -p ${SSH_PORT} deploy@$(hostname -I | awk '{print $1}')"
echo "2. Update pocketquant-config/vps/default/host with: deploy@$(hostname -I | awk '{print $1}')"
echo "3. git push from pocketquant-config, then push to pocketquant (or: gh workflow run cicd.yml)"
echo ""
echo "CI/CD fetches host, SSH key, prod .env, Docker Hub + Portainer creds from"
echo "pocketquant-config via the POCKETQUANT_CONFIG_DEPLOY_KEY secret. No per-host"
echo "GitHub secrets/vars to set here — see docs/deployment.md → 'VPS Migration (new VPS)'."
