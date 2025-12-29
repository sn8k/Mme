#!/bin/bash
# File Version: 1.0.0
# ============================================================================
# Motion Frontend - Installateur pour Raspberry Pi OS (Debian Trixie)
# ============================================================================
# Repository: https://github.com/sn8k/Mme
#
# Usage:
#   Installation rapide (branche main):
#     curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash
#
#   Installation avec choix de branche:
#     curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --branch
#
#   Désinstallation:
#     curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall
#
#   Ou si le script est déjà téléchargé:
#     sudo ./install_motion_frontend.sh [--branch] [--uninstall] [--help]
#
# ============================================================================

set -e

# ============================================================================
# Configuration
# ============================================================================

GITHUB_OWNER="sn8k"
GITHUB_REPO="Mme"
GITHUB_API_URL="https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}"
GITHUB_RAW_URL="https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}"

# Installation paths
INSTALL_DIR="/opt/motion-frontend"
CONFIG_DIR="/etc/motion-frontend"
LOG_DIR="/var/log/motion-frontend"
VENV_DIR="${INSTALL_DIR}/.venv"

# Service configuration
SERVICE_NAME="motion-frontend"
SERVICE_USER="motion-frontend"
SERVICE_GROUP="motion-frontend"

# Default settings
DEFAULT_BRANCH="main"
DEFAULT_PORT=8765
DEFAULT_HOST="0.0.0.0"

# ============================================================================
# Colors and formatting
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# ============================================================================
# Helper functions
# ============================================================================

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                  ║"
    echo "║              Motion Frontend - Installateur                      ║"
    echo "║                  Raspberry Pi OS (Trixie)                        ║"
    echo "║                                                                  ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${MAGENTA}▶${NC} ${BOLD}$1${NC}"
}

confirm() {
    local prompt="$1"
    local default="${2:-n}"
    local answer
    
    if [[ "$default" == "y" ]]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi
    
    read -r -p "$prompt" answer
    answer="${answer:-$default}"
    
    [[ "$answer" =~ ^[Yy]$ ]]
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Ce script doit être exécuté en tant que root (utilisez sudo)"
        exit 1
    fi
}

check_system() {
    log_step "Vérification du système"
    
    # Check if running on Linux
    if [[ "$(uname -s)" != "Linux" ]]; then
        log_error "Ce script est conçu pour Linux (Raspberry Pi OS)"
        exit 1
    fi
    
    # Check for Debian-based system
    if [[ ! -f /etc/debian_version ]]; then
        log_warning "Système non-Debian détecté. L'installation peut échouer."
        if ! confirm "Continuer quand même?"; then
            exit 1
        fi
    fi
    
    # Check architecture
    local arch=$(uname -m)
    log_info "Architecture: $arch"
    
    # Check Debian version
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        log_info "Système: $PRETTY_NAME"
    fi
    
    # Check if running on Raspberry Pi
    if [[ -f /proc/device-tree/model ]]; then
        local model=$(cat /proc/device-tree/model | tr -d '\0')
        log_info "Matériel: $model"
    fi
    
    log_success "Vérification du système terminée"
}

check_internet() {
    log_step "Vérification de la connexion Internet"
    
    if ! ping -c 1 github.com &> /dev/null; then
        log_error "Impossible de joindre GitHub. Vérifiez votre connexion Internet."
        exit 1
    fi
    
    log_success "Connexion Internet OK"
}

# ============================================================================
# Branch selection
# ============================================================================

fetch_branches() {
    log_info "Récupération des branches disponibles..."
    
    local branches_json
    branches_json=$(curl -sSL "${GITHUB_API_URL}/branches" 2>/dev/null)
    
    if [[ -z "$branches_json" ]]; then
        log_error "Impossible de récupérer la liste des branches"
        return 1
    fi
    
    # Extract branch names using grep/sed (works without jq)
    echo "$branches_json" | grep -o '"name": *"[^"]*"' | sed 's/"name": *"\([^"]*\)"/\1/'
}

select_branch() {
    log_step "Sélection de la branche"
    
    local branches
    branches=$(fetch_branches)
    
    if [[ -z "$branches" ]]; then
        log_warning "Impossible de récupérer les branches, utilisation de '${DEFAULT_BRANCH}'"
        SELECTED_BRANCH="$DEFAULT_BRANCH"
        return
    fi
    
    # Convert to array
    local branch_array=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && branch_array+=("$line")
    done <<< "$branches"
    
    if [[ ${#branch_array[@]} -eq 0 ]]; then
        log_warning "Aucune branche trouvée, utilisation de '${DEFAULT_BRANCH}'"
        SELECTED_BRANCH="$DEFAULT_BRANCH"
        return
    fi
    
    echo -e "\n${CYAN}Branches disponibles:${NC}"
    echo "─────────────────────"
    
    local i=1
    for branch in "${branch_array[@]}"; do
        if [[ "$branch" == "$DEFAULT_BRANCH" ]]; then
            echo -e "  ${GREEN}$i)${NC} $branch ${YELLOW}(défaut)${NC}"
        else
            echo -e "  ${GREEN}$i)${NC} $branch"
        fi
        ((i++))
    done
    
    echo ""
    read -r -p "Choisissez une branche (1-${#branch_array[@]}) ou appuyez sur Entrée pour '${DEFAULT_BRANCH}': " choice
    
    if [[ -z "$choice" ]]; then
        SELECTED_BRANCH="$DEFAULT_BRANCH"
    elif [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le ${#branch_array[@]} ]]; then
        SELECTED_BRANCH="${branch_array[$((choice-1))]}"
    else
        log_warning "Choix invalide, utilisation de '${DEFAULT_BRANCH}'"
        SELECTED_BRANCH="$DEFAULT_BRANCH"
    fi
    
    log_success "Branche sélectionnée: ${SELECTED_BRANCH}"
}

# ============================================================================
# Installation functions
# ============================================================================

install_system_dependencies() {
    log_step "Installation des dépendances système"
    
    # Update package list
    log_info "Mise à jour des listes de paquets..."
    apt-get update -qq
    
    # Install required packages
    local packages=(
        python3
        python3-pip
        python3-venv
        python3-dev
        git
        curl
        wget
        build-essential
        libffi-dev
        libssl-dev
        libjpeg-dev
        zlib1g-dev
        libopencv-dev
        python3-opencv
        ffmpeg
        v4l-utils
        alsa-utils
    )
    
    log_info "Installation des paquets: ${packages[*]}"
    apt-get install -y "${packages[@]}" || {
        log_warning "Certains paquets n'ont pas pu être installés"
    }
    
    log_success "Dépendances système installées"
}

create_user_and_groups() {
    log_step "Configuration de l'utilisateur et des groupes"
    
    # Create service group if it doesn't exist
    if ! getent group "$SERVICE_GROUP" > /dev/null 2>&1; then
        log_info "Création du groupe '$SERVICE_GROUP'..."
        groupadd --system "$SERVICE_GROUP"
    else
        log_info "Le groupe '$SERVICE_GROUP' existe déjà"
    fi
    
    # Create service user if it doesn't exist
    if ! id "$SERVICE_USER" > /dev/null 2>&1; then
        log_info "Création de l'utilisateur '$SERVICE_USER'..."
        useradd --system \
            --gid "$SERVICE_GROUP" \
            --home-dir "$INSTALL_DIR" \
            --shell /usr/sbin/nologin \
            --comment "Motion Frontend Service" \
            "$SERVICE_USER"
    else
        log_info "L'utilisateur '$SERVICE_USER' existe déjà"
    fi
    
    # Add user to required groups for camera and audio access
    local groups_to_add=(video audio gpio i2c spi)
    
    for grp in "${groups_to_add[@]}"; do
        if getent group "$grp" > /dev/null 2>&1; then
            if ! groups "$SERVICE_USER" | grep -qw "$grp"; then
                log_info "Ajout de '$SERVICE_USER' au groupe '$grp'..."
                usermod -aG "$grp" "$SERVICE_USER"
            else
                log_info "'$SERVICE_USER' est déjà membre de '$grp'"
            fi
        fi
    done
    
    log_success "Utilisateur et groupes configurés"
}

create_directories() {
    log_step "Création des répertoires"
    
    # Create installation directory
    if [[ -d "$INSTALL_DIR" ]]; then
        log_warning "Le répertoire '$INSTALL_DIR' existe déjà"
        if confirm "Voulez-vous le supprimer et réinstaller?"; then
            rm -rf "$INSTALL_DIR"
        else
            log_error "Installation annulée"
            exit 1
        fi
    fi
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    
    log_success "Répertoires créés"
}

download_source() {
    log_step "Téléchargement du code source (branche: ${SELECTED_BRANCH})"
    
    local download_url="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/archive/refs/heads/${SELECTED_BRANCH}.zip"
    local temp_zip="/tmp/motion-frontend-${SELECTED_BRANCH}.zip"
    local temp_dir="/tmp/motion-frontend-extract"
    
    # Download archive
    log_info "Téléchargement depuis: $download_url"
    if ! curl -sSL -o "$temp_zip" "$download_url"; then
        log_error "Échec du téléchargement"
        exit 1
    fi
    
    # Extract archive
    log_info "Extraction de l'archive..."
    rm -rf "$temp_dir"
    mkdir -p "$temp_dir"
    unzip -q "$temp_zip" -d "$temp_dir"
    
    # Move files to installation directory
    # GitHub archives contain a top-level directory named "repo-branch"
    local extracted_dir=$(ls -d "$temp_dir"/*/ | head -n 1)
    
    if [[ -z "$extracted_dir" ]]; then
        log_error "Impossible de trouver le répertoire extrait"
        exit 1
    fi
    
    log_info "Copie des fichiers vers $INSTALL_DIR..."
    cp -r "$extracted_dir"/* "$INSTALL_DIR/"
    
    # Cleanup
    rm -rf "$temp_zip" "$temp_dir"
    
    log_success "Code source téléchargé et extrait"
}

setup_python_environment() {
    log_step "Configuration de l'environnement Python"
    
    # Create virtual environment
    log_info "Création de l'environnement virtuel..."
    python3 -m venv "$VENV_DIR"
    
    # Upgrade pip
    log_info "Mise à jour de pip..."
    "$VENV_DIR/bin/pip" install --upgrade pip wheel setuptools
    
    # Install requirements
    if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
        log_info "Installation des dépendances Python..."
        "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    else
        log_warning "Fichier requirements.txt non trouvé"
    fi
    
    log_success "Environnement Python configuré"
}

setup_configuration() {
    log_step "Configuration de l'application"
    
    # Create config directory in installation if it doesn't exist
    local app_config_dir="$INSTALL_DIR/config"
    mkdir -p "$app_config_dir"
    
    # Copy default configuration if it exists and config doesn't exist yet
    if [[ -f "$INSTALL_DIR/config/motion_frontend.json" ]]; then
        log_info "Configuration par défaut trouvée"
    else
        # Create minimal default configuration
        log_info "Création de la configuration par défaut..."
        cat > "$app_config_dir/motion_frontend.json" << 'EOF'
{
  "version": "1.0",
  "hostname": "motion-frontend",
  "theme": "dark",
  "language": "fr",
  "logging_level": "INFO",
  "log_to_file": true,
  "log_reset_on_start": false,
  "display": {
    "preview_count": 1,
    "preview_quality": "high"
  },
  "network": {
    "wifi_ssid": "",
    "wifi_password": "",
    "ip_mode": "dhcp"
  },
  "camera_filter_patterns": [
    "bcm2835-isp",
    "unicam",
    "rp1-cfe"
  ],
  "audio_filter_patterns": [
    "hdmi",
    "spdif"
  ]
}
EOF
    fi
    
    # Create users.json if it doesn't exist
    if [[ ! -f "$app_config_dir/users.json" ]]; then
        log_info "Création du fichier utilisateurs..."
        cat > "$app_config_dir/users.json" << 'EOF'
{
  "users": {
    "admin": {
      "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4o0sH1LcPGGXZFO2",
      "role": "admin",
      "enabled": true,
      "must_change_password": true,
      "created_at": "2025-01-01T00:00:00"
    }
  }
}
EOF
        # Note: Default password is 'admin' - user must change it on first login
    fi
    
    log_success "Configuration créée"
}

set_permissions() {
    log_step "Configuration des permissions"
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
    
    # Set permissions
    chmod -R 755 "$INSTALL_DIR"
    chmod -R 750 "$INSTALL_DIR/config"
    chmod 640 "$INSTALL_DIR/config"/*.json 2>/dev/null || true
    chmod -R 755 "$LOG_DIR"
    
    # Make scripts executable
    chmod +x "$INSTALL_DIR/scripts"/*.sh 2>/dev/null || true
    
    log_success "Permissions configurées"
}

create_systemd_service() {
    log_step "Création du service systemd"
    
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    
    cat > "$service_file" << EOF
[Unit]
Description=Motion Frontend - Web Interface for Video Surveillance
Documentation=https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"

ExecStart=${VENV_DIR}/bin/python -m backend.server \\
    --host ${DEFAULT_HOST} \\
    --port ${DEFAULT_PORT} \\
    --root ${INSTALL_DIR}

Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${INSTALL_DIR}/config ${INSTALL_DIR}/logs ${LOG_DIR}
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload
    
    # Enable service
    systemctl enable "$SERVICE_NAME"
    
    log_success "Service systemd créé et activé"
}

start_service() {
    log_step "Démarrage du service"
    
    systemctl start "$SERVICE_NAME"
    
    # Wait a moment and check status
    sleep 2
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service démarré avec succès"
    else
        log_warning "Le service n'a pas démarré correctement"
        log_info "Vérifiez les logs avec: journalctl -u $SERVICE_NAME -f"
    fi
}

print_installation_summary() {
    local ip_address
    ip_address=$(hostname -I | awk '{print $1}')
    
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                  Installation terminée !                         ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}Informations:${NC}"
    echo "─────────────────────────────────────────────────────────────────────"
    echo -e "  Répertoire d'installation : ${CYAN}${INSTALL_DIR}${NC}"
    echo -e "  Configuration             : ${CYAN}${INSTALL_DIR}/config${NC}"
    echo -e "  Logs                      : ${CYAN}${LOG_DIR}${NC}"
    echo -e "  Branche installée         : ${CYAN}${SELECTED_BRANCH}${NC}"
    echo -e "  Service                   : ${CYAN}${SERVICE_NAME}${NC}"
    echo ""
    echo -e "${BOLD}Accès à l'interface:${NC}"
    echo "─────────────────────────────────────────────────────────────────────"
    echo -e "  URL locale    : ${CYAN}http://localhost:${DEFAULT_PORT}${NC}"
    if [[ -n "$ip_address" ]]; then
        echo -e "  URL réseau    : ${CYAN}http://${ip_address}:${DEFAULT_PORT}${NC}"
    fi
    echo ""
    echo -e "${BOLD}Identifiants par défaut:${NC}"
    echo "─────────────────────────────────────────────────────────────────────"
    echo -e "  Utilisateur   : ${YELLOW}admin${NC}"
    echo -e "  Mot de passe  : ${YELLOW}admin${NC} ${RED}(à changer à la première connexion)${NC}"
    echo ""
    echo -e "${BOLD}Commandes utiles:${NC}"
    echo "─────────────────────────────────────────────────────────────────────"
    echo -e "  Statut        : ${WHITE}sudo systemctl status ${SERVICE_NAME}${NC}"
    echo -e "  Démarrer      : ${WHITE}sudo systemctl start ${SERVICE_NAME}${NC}"
    echo -e "  Arrêter       : ${WHITE}sudo systemctl stop ${SERVICE_NAME}${NC}"
    echo -e "  Redémarrer    : ${WHITE}sudo systemctl restart ${SERVICE_NAME}${NC}"
    echo -e "  Logs          : ${WHITE}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
    echo ""
    echo -e "${BOLD}Désinstallation:${NC}"
    echo "─────────────────────────────────────────────────────────────────────"
    echo -e "  ${WHITE}curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall${NC}"
    echo ""
}

# ============================================================================
# Uninstallation functions
# ============================================================================

uninstall() {
    print_banner
    
    log_step "Désinstallation de Motion Frontend"
    
    if ! confirm "Êtes-vous sûr de vouloir désinstaller Motion Frontend?" "n"; then
        log_info "Désinstallation annulée"
        exit 0
    fi
    
    # Stop and disable service
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        log_info "Arrêt du service..."
        systemctl stop "$SERVICE_NAME"
    fi
    
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        log_info "Désactivation du service..."
        systemctl disable "$SERVICE_NAME"
    fi
    
    # Remove service file
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    if [[ -f "$service_file" ]]; then
        log_info "Suppression du fichier service..."
        rm -f "$service_file"
        systemctl daemon-reload
    fi
    
    # Ask about configuration preservation
    local remove_config=false
    if [[ -d "$INSTALL_DIR/config" ]]; then
        if confirm "Voulez-vous également supprimer les fichiers de configuration?" "n"; then
            remove_config=true
        else
            log_info "Les fichiers de configuration seront préservés dans ${INSTALL_DIR}/config"
            # Backup config
            local backup_dir="/tmp/motion-frontend-config-backup-$(date +%Y%m%d%H%M%S)"
            mkdir -p "$backup_dir"
            cp -r "$INSTALL_DIR/config"/* "$backup_dir/" 2>/dev/null || true
            log_info "Configuration sauvegardée dans: $backup_dir"
        fi
    fi
    
    # Remove installation directory
    if [[ -d "$INSTALL_DIR" ]]; then
        log_info "Suppression du répertoire d'installation..."
        rm -rf "$INSTALL_DIR"
    fi
    
    # Remove log directory
    if [[ -d "$LOG_DIR" ]]; then
        log_info "Suppression des logs..."
        rm -rf "$LOG_DIR"
    fi
    
    # Remove config directory if requested
    if [[ "$remove_config" == true ]] && [[ -d "$CONFIG_DIR" ]]; then
        log_info "Suppression de la configuration..."
        rm -rf "$CONFIG_DIR"
    fi
    
    # Remove user (optional)
    if id "$SERVICE_USER" > /dev/null 2>&1; then
        if confirm "Voulez-vous supprimer l'utilisateur système '$SERVICE_USER'?" "n"; then
            log_info "Suppression de l'utilisateur..."
            userdel "$SERVICE_USER" 2>/dev/null || true
        fi
    fi
    
    # Remove group (optional)
    if getent group "$SERVICE_GROUP" > /dev/null 2>&1; then
        if confirm "Voulez-vous supprimer le groupe système '$SERVICE_GROUP'?" "n"; then
            log_info "Suppression du groupe..."
            groupdel "$SERVICE_GROUP" 2>/dev/null || true
        fi
    fi
    
    echo ""
    log_success "Désinstallation terminée"
    echo ""
    echo -e "${YELLOW}Note:${NC} Les dépendances système (python3, ffmpeg, etc.) n'ont pas été supprimées."
    echo ""
}

# ============================================================================
# Update function
# ============================================================================

update() {
    print_banner
    
    log_step "Mise à jour de Motion Frontend"
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "Motion Frontend n'est pas installé dans $INSTALL_DIR"
        log_info "Utilisez l'installation normale pour installer le projet"
        exit 1
    fi
    
    # Stop service
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        log_info "Arrêt du service..."
        systemctl stop "$SERVICE_NAME"
    fi
    
    # Backup current config
    local backup_dir="/tmp/motion-frontend-config-backup-$(date +%Y%m%d%H%M%S)"
    if [[ -d "$INSTALL_DIR/config" ]]; then
        log_info "Sauvegarde de la configuration..."
        mkdir -p "$backup_dir"
        cp -r "$INSTALL_DIR/config"/* "$backup_dir/"
    fi
    
    # Download new source
    download_source
    
    # Restore config
    if [[ -d "$backup_dir" ]]; then
        log_info "Restauration de la configuration..."
        cp -r "$backup_dir"/* "$INSTALL_DIR/config/"
        rm -rf "$backup_dir"
    fi
    
    # Update Python dependencies
    setup_python_environment
    
    # Fix permissions
    set_permissions
    
    # Start service
    start_service
    
    log_success "Mise à jour terminée"
}

# ============================================================================
# Main installation
# ============================================================================

install() {
    print_banner
    
    check_root
    check_system
    check_internet
    
    # Select branch if requested
    if [[ "$SELECT_BRANCH" == true ]]; then
        select_branch
    else
        SELECTED_BRANCH="$DEFAULT_BRANCH"
        log_info "Utilisation de la branche: $SELECTED_BRANCH"
    fi
    
    echo ""
    log_info "L'installation va commencer avec les paramètres suivants:"
    echo "  - Branche: $SELECTED_BRANCH"
    echo "  - Répertoire: $INSTALL_DIR"
    echo "  - Port: $DEFAULT_PORT"
    echo ""
    
    if ! confirm "Continuer l'installation?" "y"; then
        log_info "Installation annulée"
        exit 0
    fi
    
    install_system_dependencies
    create_user_and_groups
    create_directories
    download_source
    setup_python_environment
    setup_configuration
    set_permissions
    create_systemd_service
    start_service
    print_installation_summary
}

# ============================================================================
# Help
# ============================================================================

show_help() {
    echo "Motion Frontend - Installateur pour Raspberry Pi OS"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --help, -h        Affiche cette aide"
    echo "  --branch, -b      Affiche un menu pour choisir la branche à installer"
    echo "  --uninstall, -u   Désinstalle Motion Frontend"
    echo "  --update          Met à jour l'installation existante"
    echo ""
    echo "Installation rapide (branche main):"
    echo "  curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash"
    echo ""
    echo "Installation avec choix de branche:"
    echo "  curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- --branch"
    echo ""
    echo "Désinstallation:"
    echo "  curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall"
    echo ""
}

# ============================================================================
# Main entry point
# ============================================================================

main() {
    local action="install"
    SELECT_BRANCH=false
    SELECTED_BRANCH="$DEFAULT_BRANCH"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                show_help
                exit 0
                ;;
            --branch|-b)
                SELECT_BRANCH=true
                shift
                ;;
            --uninstall|-u)
                action="uninstall"
                shift
                ;;
            --update)
                action="update"
                shift
                ;;
            *)
                log_error "Option inconnue: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Execute action
    case "$action" in
        install)
            install
            ;;
        uninstall)
            check_root
            uninstall
            ;;
        update)
            check_root
            if [[ "$SELECT_BRANCH" == true ]]; then
                select_branch
            fi
            update
            ;;
    esac
}

# Run main function
main "$@"
