#!/usr/bin/env bash
# =============================================================================
#  AgroDock — instalação no servidor (Ubuntu 22.04 / 24.04)
#
#  Deixa o sistema rodando sozinho, 24 horas por dia:
#    * ambiente Python isolado em .venv
#    * serviço do systemd (sobe junto com o servidor e reinicia se cair)
#    * Nginx na frente, na porta 80 (e 443 depois do certificado)
#    * firewall do Ubuntu liberado para 80 e 443
#    * backup do banco todo dia de madrugada
#
#  Uso:
#      sudo bash deploy/instalar.sh                 # sem domínio (acessa pelo IP)
#      sudo bash deploy/instalar.sh meusite.com.br  # com domínio
#
#  Rode de dentro da pasta do AgroDock. Pode rodar de novo quando quiser:
#  o script não apaga o banco nem repete o que já está feito.
# =============================================================================
set -euo pipefail

DOMINIO="${1:-}"
PASTA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICO="agrodock"
PORTA_INTERNA=8000

# usuário que vai rodar o sistema: o dono da pasta (ubuntu, opc, galba...)
DONO="$(stat -c '%U' "$PASTA")"
[ "$DONO" = "root" ] && DONO="${SUDO_USER:-root}"

azul()  { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
aviso() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode com sudo:  sudo bash deploy/instalar.sh ${DOMINIO}"
  exit 1
fi

azul "AgroDock — instalando em $PASTA (usuário $DONO)"

# ---------------------------------------------------------------- 1. pacotes
azul "1/7  Instalando o que falta no servidor"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx sqlite3 curl >/dev/null
ok "Python, Nginx e utilitários prontos"

# ------------------------------------------------------------- 2. ambiente
azul "2/7  Preparando o ambiente do sistema"
if [ ! -d "$PASTA/.venv" ]; then
  sudo -u "$DONO" python3 -m venv "$PASTA/.venv"
fi
sudo -u "$DONO" "$PASTA/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$DONO" "$PASTA/.venv/bin/pip" install --quiet -r "$PASTA/requirements.txt"
mkdir -p "$PASTA/dados" "$PASTA/backups"
chown -R "$DONO":"$DONO" "$PASTA/dados" "$PASTA/backups"
ok "Dependências instaladas"

# ------------------------------------------------ 3. chave secreta da sessão
azul "3/7  Gerando a chave de segurança das sessões"
ENV_FILE="$PASTA/deploy/agrodock.env"
if [ ! -f "$ENV_FILE" ]; then
  CHAVE="$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=' | head -c 50)"
  cat > "$ENV_FILE" <<EOF
# Configuração do AgroDock neste servidor. NÃO compartilhe este arquivo.
# A chave abaixo assina as sessões: se mudar, todo mundo precisa entrar de novo.
FIN_SECRET_KEY=$CHAVE
FIN_TOKEN_HORAS=12

# Banco de dados. Sem a linha abaixo, o sistema usa o arquivo dados/financeiro.db
# deste servidor. Para usar um PostgreSQL na nuvem (Neon, Supabase...), tire o "#"
# e cole o endereço; depois: sudo systemctl restart agrodock
#FIN_DATABASE_URL=postgresql://usuario:senha@host/banco?sslmode=require
EOF
  chmod 600 "$ENV_FILE"
  chown "$DONO":"$DONO" "$ENV_FILE"
  ok "Chave nova criada em deploy/agrodock.env"
else
  ok "Chave que já existia foi mantida"
fi

# ---------------------------------------------------------------- 4. serviço
azul "4/7  Criando o serviço que mantém o sistema no ar"
cat > "/etc/systemd/system/$SERVICO.service" <<EOF
[Unit]
Description=AgroDock — Contratos e Gestão
After=network.target

[Service]
Type=simple
User=$DONO
WorkingDirectory=$PASTA
EnvironmentFile=$ENV_FILE
ExecStart=$PASTA/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port $PORTA_INTERNA \\
          --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=5
StandardOutput=append:$PASTA/dados/agrodock.log
StandardError=append:$PASTA/dados/agrodock.log

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --quiet "$SERVICO"
systemctl restart "$SERVICO"
sleep 3
if systemctl is-active --quiet "$SERVICO"; then
  ok "Serviço no ar (systemctl status $SERVICO)"
else
  aviso "O serviço não subiu. Veja o motivo com: journalctl -u $SERVICO -n 40"
  exit 1
fi

# ------------------------------------------------------------------ 5. Nginx
azul "5/7  Colocando o Nginx na frente"
NOME_SERVIDOR="${DOMINIO:-_}"
cat > "/etc/nginx/sites-available/$SERVICO" <<EOF
server {
    listen 80;
    server_name $NOME_SERVIDOR;

    # limite generoso: o logotipo da empresa vai por dentro do formulário
    client_max_body_size 12M;

    location / {
        proxy_pass http://127.0.0.1:$PORTA_INTERNA;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF
ln -sf "/etc/nginx/sites-available/$SERVICO" "/etc/nginx/sites-enabled/$SERVICO"
rm -f /etc/nginx/sites-enabled/default
nginx -t >/dev/null 2>&1 && systemctl reload nginx
ok "Nginx respondendo na porta 80"

# --------------------------------------------------------------- 6. firewall
azul "6/7  Liberando as portas 80 e 443 no Ubuntu"
# A imagem do Ubuntu na Oracle vem com tudo fechado, menos a porta 22.
iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || \
  iptables -I INPUT 6 -p tcp --dport 80 -j ACCEPT
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || \
  iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT
if command -v netfilter-persistent >/dev/null 2>&1; then
  netfilter-persistent save >/dev/null 2>&1 || true
else
  apt-get install -y -qq iptables-persistent >/dev/null 2>&1 || true
  command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save >/dev/null 2>&1 || true
fi
ok "Portas liberadas (e salvas para o próximo boot)"
aviso "Falta liberar as mesmas portas no painel da Oracle (Security List da VCN)"

# ----------------------------------------------------------------- 7. backup
azul "7/7  Programando o backup do banco"
chmod +x "$PASTA/deploy/backup.sh" 2>/dev/null || true
cat > /etc/cron.d/agrodock-backup <<EOF
# Backup do banco do AgroDock, todo dia às 3h da manhã
0 3 * * * $DONO $PASTA/deploy/backup.sh >> $PASTA/dados/backup.log 2>&1
EOF
ok "Backup diário programado para as 3h (pasta backups/)"

# ------------------------------------------------------------------ HTTPS
if [ -n "$DOMINIO" ]; then
  azul "Extra  Certificado HTTPS para $DOMINIO"
  apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
  if certbot --nginx -d "$DOMINIO" --non-interactive --agree-tos \
       --register-unsafely-without-email --redirect >/dev/null 2>&1; then
    ok "HTTPS ativo — https://$DOMINIO"
  else
    aviso "O certificado falhou. Confira se o domínio já aponta para o IP deste servidor"
    aviso "e rode de novo:  sudo certbot --nginx -d $DOMINIO"
  fi
fi

IP="$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || true)"
if ! printf '%s' "$IP" | grep -qE '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
  IP="o-IP-que-aparece-no-painel-da-Oracle"
fi
azul "Pronto!"
cat <<EOF
  Endereço:  ${DOMINIO:+https://$DOMINIO}${DOMINIO:-http://$IP}
  Entrar:    admin@financeiro.local  /  admin123   (troque a senha hoje)

  Comandos do dia a dia:
    sudo systemctl status agrodock     ver se está no ar
    sudo systemctl restart agrodock    reiniciar
    tail -f dados/agrodock.log         acompanhar o que acontece
    bash deploy/atualizar.sh           aplicar uma versão nova
    bash deploy/backup.sh              backup na hora

EOF
