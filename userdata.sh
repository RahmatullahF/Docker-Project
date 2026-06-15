#!/bin/bash
cd /home/ubuntu
apt update -y
apt install python3 python3-pip python3-venv curl mysql-client nginx -y
git clone https://${USER}:${GIT_TOKEN}@github.com/${USER}/${REPO}.git
cd /home/ubuntu/${REPO}
cat dbendpoint >> .env
chown -R ubuntu:ubuntu /home/ubuntu/${REPO}
chmod -R 755 /home/ubuntu/${REPO}
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
chmod 755 static/images
chmod 755 templates
set -a
source .env
set +a
envsubst '${DOMAIN_NAME}' < nginx.template > ./${APP_NAME}
envsubst < gunicorn.service.template > ./${APP_NAME}.service
cp ${APP_NAME} /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
cp ./${APP_NAME}.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ${APP_NAME}
systemctl enable nginx
systemctl restart nginx
systemctl restart ${APP_NAME}