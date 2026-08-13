#!/usr/bin/env bash
# Bootstrap Oracle Cloud Ubuntu instance for Aurynix Nexus
# Run once on a fresh server: bash scripts/setup-server.sh

set -euo pipefail

echo "=== Aurynix Server Setup ==="

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker "$USER"

# Install nginx + certbot
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Open required ports (Oracle Cloud uses iptables on top of Security Lists)
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 22 -j ACCEPT
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save

# Create app directory
sudo mkdir -p /opt/aurynix
sudo chown "$USER":"$USER" /opt/aurynix

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Log out and back in (docker group takes effect)"
echo "  2. cd /opt/aurynix && git clone https://github.com/Aurynix/aurynix-nexus.git app"
echo "  3. cp app/.env.example app/.env && nano app/.env"
echo "  4. cd app && docker compose up -d --build"
echo "  5. docker compose exec app python scripts/init_db.py"
