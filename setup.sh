#!/bin/bash
# AIVO Setup Script - Install and configure AIVO as a system service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 AIVO Service Setup Script${NC}"
echo "=================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}❌ This script should not be run as root${NC}"
   echo "Please run as a regular user with sudo privileges"
   exit 1
fi

# Create aivo user if it doesn't exist
if ! id "aivo" &>/dev/null; then
    echo -e "${YELLOW}👤 Creating aivo user...${NC}"
    sudo useradd -r -s /bin/bash -d /home/aivo -m aivo
    sudo usermod -a -G audio aivo
    echo -e "${GREEN}✅ User 'aivo' created${NC}"
else
    echo -e "${GREEN}✅ User 'aivo' already exists${NC}"
    sudo usermod -a -G audio aivo
fi

# Create log directory
echo -e "${YELLOW}📁 Creating log directory...${NC}"
sudo mkdir -p /var/log/aivo
sudo chown aivo:aivo /var/log/aivo
sudo chmod 755 /var/log/aivo

# Copy project to aivo user directory
echo -e "${YELLOW}📂 Setting up project directory...${NC}"
sudo mkdir -p /home/aivo/aivo-py
sudo cp -r . /home/aivo/aivo-py/
sudo chown -R aivo:aivo /home/aivo/aivo-py
sudo chmod +x /home/aivo/aivo-py/app/entry.py
sudo chmod +x /home/aivo/aivo-py/app/scheduler.py

# Update service file paths
echo -e "${YELLOW}🔧 Updating service files...${NC}"
sed -i 's|/home/aivo/aivo-py|'$(pwd)'|g' aivo-recorder.service
sed -i 's|/home/aivo/aivo-py|'$(pwd)'|g' aivo-scheduler.service

# Install systemd service files
echo -e "${YELLOW}⚙️  Installing systemd services...${NC}"
sudo cp aivo-recorder.service /etc/systemd/system/
sudo cp aivo-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable services (but don't start yet)
echo -e "${YELLOW}🔄 Enabling services...${NC}"
sudo systemctl enable aivo-recorder.service
sudo systemctl enable aivo-scheduler.service

echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo -e "${BLUE}📋 Next Steps:${NC}"
echo "1. Set up your .env file with required environment variables:"
echo "   - DB_URL (PostgreSQL connection string)"
echo "   - GEMINI_API_KEY (optional, for AI summaries)"
echo ""
echo "2. Install Python dependencies:"
echo "   pip install -r requirements.txt"
echo ""
echo "3. Test the installation:"
echo "   python main.py health"
echo ""
echo "4. Start the services:"
echo "   sudo systemctl start aivo-recorder"
echo "   sudo systemctl start aivo-scheduler"
echo ""
echo "5. Check service status:"
echo "   sudo systemctl status aivo-recorder"
echo "   sudo systemctl status aivo-scheduler"
echo ""
echo "6. View logs:"
echo "   sudo journalctl -u aivo-recorder -f"
echo "   sudo journalctl -u aivo-scheduler -f"
echo ""
echo -e "${GREEN}🎉 AIVO is ready to run!${NC}"