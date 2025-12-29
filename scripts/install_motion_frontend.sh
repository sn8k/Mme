#!/bin/bash
# File Version: 1.5.4
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
#   Réparation:
#     curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --repair
#
#   Désinstallation:
#     curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall
#
#   Ou si le script est déjà téléchargé:
#     sudo ./install_motion_frontend.sh [--branch] [--uninstall] [--repair] [--help]
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

# Meeting service settings
# Server URL is fixed and cannot be changed
MEETING_SERVER_URL="https://meeting.ygsoft.fr"
MEETING_DEVICE_KEY=""
MEETING_TOKEN_CODE=""
MEETING_VALIDATED=false

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

# Script version (extracted from header)
SCRIPT_VERSION="1.5.4"

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
    echo "║                      Version: ${SCRIPT_VERSION}                            ║"
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
# Meeting service configuration
# ============================================================================

configure_meeting_service() {
    log_step "Configuration du service Meeting"
    
    echo ""
    echo -e "${CYAN}Le service Meeting permet de signaler l'état en ligne de l'appareil${NC}"
    echo -e "${CYAN}à un serveur central (heartbeat).${NC}"
    echo -e "${CYAN}Serveur Meeting: ${WHITE}${MEETING_SERVER_URL}${NC}"
    echo ""
    
    if ! confirm "Voulez-vous configurer le service Meeting maintenant?" "n"; then
        log_info "Configuration Meeting ignorée (peut être configuré plus tard via l'interface web)"
        return 0
    fi
    
    echo ""
    
    # Device Key
    echo -e "${YELLOW}La Device Key est l'identifiant unique de cet appareil.${NC}"
    echo -e "${YELLOW}Format: chaîne hexadécimale (ex: F743F2371A834C31B56B3B47708064FF)${NC}"
    
    while [[ -z "$MEETING_DEVICE_KEY" ]]; do
        read -r -p "Device Key: " input_device_key
        if [[ -n "$input_device_key" ]]; then
            MEETING_DEVICE_KEY="$input_device_key"
        else
            log_warning "La Device Key est obligatoire pour la configuration Meeting"
            if ! confirm "Réessayer?" "y"; then
                log_info "Configuration Meeting annulée"
                return 0
            fi
        fi
    done
    
    # Token Code
    echo ""
    echo -e "${YELLOW}Le Token Code est le code d'authentification associé à ce device.${NC}"
    
    while [[ -z "$MEETING_TOKEN_CODE" ]]; do
        read -r -p "Token Code: " input_token
        if [[ -n "$input_token" ]]; then
            MEETING_TOKEN_CODE="$input_token"
        else
            log_warning "Le Token Code est obligatoire pour la configuration Meeting"
            if ! confirm "Réessayer?" "y"; then
                log_info "Configuration Meeting annulée"
                MEETING_DEVICE_KEY=""
                return 0
            fi
        fi
    done
    
    # Validate with Meeting server
    echo ""
    log_info "Vérification des informations sur le serveur Meeting..."
    
    if ! validate_meeting_credentials; then
        # Error already displayed by validate_meeting_credentials
        exit 1
    fi
    
    MEETING_VALIDATED=true
    log_success "Configuration Meeting validée et token consommé"
}

# Validate Meeting credentials and burn a token
validate_meeting_credentials() {
    local api_url="${MEETING_SERVER_URL}/api/devices/${MEETING_DEVICE_KEY}"
    
    # Step 1: Check device exists and get info
    log_info "Vérification du device sur ${MEETING_SERVER_URL}..."
    
    local response
    response=$(curl -sSL -w "\n%{http_code}" "$api_url" 2>/dev/null)
    
    local http_code
    http_code=$(echo "$response" | tail -n 1)
    local body
    body=$(echo "$response" | sed '$d')
    
    if [[ "$http_code" != "200" ]]; then
        echo ""
        log_error "═══════════════════════════════════════════════════════════════"
        log_error "ERREUR: Device non trouvé sur le serveur Meeting"
        log_error "═══════════════════════════════════════════════════════════════"
        echo ""
        echo -e "${RED}La Device Key '${MEETING_DEVICE_KEY}' n'existe pas${NC}"
        echo -e "${RED}ou n'est pas accessible sur ${MEETING_SERVER_URL}${NC}"
        echo ""
        echo -e "${YELLOW}Vérifiez que:${NC}"
        echo "  1. La Device Key est correcte"
        echo "  2. Le device a été créé sur le serveur Meeting"
        echo "  3. Le serveur Meeting est accessible"
        echo ""
        return 1
    fi
    
    # Step 2: Verify token_code matches (extract from response)
    local stored_token
    stored_token=$(echo "$body" | grep -o '"token_code"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:.*"\([^"]*\)"/\1/')
    
    if [[ "$stored_token" != "$MEETING_TOKEN_CODE" ]]; then
        echo ""
        log_error "═══════════════════════════════════════════════════════════════"
        log_error "ERREUR: Token Code invalide"
        log_error "═══════════════════════════════════════════════════════════════"
        echo ""
        echo -e "${RED}Le Token Code fourni ne correspond pas à celui${NC}"
        echo -e "${RED}enregistré sur le serveur Meeting pour ce device.${NC}"
        echo ""
        return 1
    fi
    
    log_success "Device Key et Token Code vérifiés"
    
    # Step 3: Check available tokens
    local token_count
    token_count=$(echo "$body" | grep -o '"token_count"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$')
    
    if [[ -z "$token_count" ]] || [[ "$token_count" -le 0 ]]; then
        echo ""
        log_error "═══════════════════════════════════════════════════════════════"
        log_error "ERREUR: Aucun token disponible"
        log_error "═══════════════════════════════════════════════════════════════"
        echo ""
        echo -e "${RED}Ce device n'a plus de tokens d'installation disponibles.${NC}"
        echo ""
        echo -e "${YELLOW}Chaque installation de Motion Frontend consomme un token.${NC}"
        echo -e "${YELLOW}Les tokens sont gérés par l'administrateur du serveur Meeting.${NC}"
        echo ""
        echo -e "${WHITE}Pour obtenir des tokens supplémentaires:${NC}"
        echo "  1. Connectez-vous au serveur Meeting"
        echo "  2. Accédez à la gestion du device: ${MEETING_DEVICE_KEY}"
        echo "  3. Ajoutez des tokens via l'interface d'administration"
        echo ""
        echo -e "${CYAN}Endpoint d'administration:${NC}"
        echo "  PUT ${MEETING_SERVER_URL}/api/devices/${MEETING_DEVICE_KEY}/tokens"
        echo "  Body: { \"token_count\": N }"
        echo ""
        return 1
    fi
    
    log_info "Tokens disponibles: ${token_count}"
    
    # Step 4: Burn a token (flash-request)
    log_info "Consommation d'un token d'installation..."
    
    local flash_response
    flash_response=$(curl -sSL -w "\n%{http_code}" -X POST "$api_url/flash-request" 2>/dev/null)
    
    local flash_http_code
    flash_http_code=$(echo "$flash_response" | tail -n 1)
    local flash_body
    flash_body=$(echo "$flash_response" | sed '$d')
    
    if [[ "$flash_http_code" != "200" ]]; then
        echo ""
        log_error "═══════════════════════════════════════════════════════════════"
        log_error "ERREUR: Impossible de consommer le token"
        log_error "═══════════════════════════════════════════════════════════════"
        echo ""
        echo -e "${RED}L'appel à flash-request a échoué (HTTP ${flash_http_code})${NC}"
        echo ""
        echo -e "${YELLOW}Réponse du serveur:${NC}"
        echo "$flash_body"
        echo ""
        return 1
    fi
    
    # Extract remaining tokens
    local tokens_left
    tokens_left=$(echo "$flash_body" | grep -o '"tokens_left"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$')
    
    log_success "Token consommé avec succès (restants: ${tokens_left:-?})"
    
    return 0
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

install_mediamtx() {
    log_step "Installation de MediaMTX (serveur RTSP)"
    
    # Check if already installed
    if command -v mediamtx &> /dev/null; then
        local current_version
        current_version=$(mediamtx --version 2>/dev/null | head -n1 || echo "unknown")
        log_info "MediaMTX est déjà installé: $current_version"
        return 0
    fi
    
    # Detect architecture
    local arch
    arch=$(uname -m)
    local mediamtx_arch=""
    
    case "$arch" in
        aarch64|arm64)
            mediamtx_arch="arm64"
            ;;
        armv7l|armhf)
            mediamtx_arch="armv7"
            ;;
        x86_64|amd64)
            mediamtx_arch="amd64"
            ;;
        *)
            log_warning "Architecture non supportée pour MediaMTX: $arch"
            log_warning "Le streaming RTSP ne sera pas disponible"
            return 1
            ;;
    esac
    
    # Get latest release version from GitHub
    log_info "Récupération de la dernière version de MediaMTX..."
    local latest_version
    local api_response
    api_response=$(curl -sSL "https://api.github.com/repos/bluenviron/mediamtx/releases/latest" 2>/dev/null)
    
    if [[ -z "$api_response" ]]; then
        log_warning "Impossible de contacter l'API GitHub"
        log_warning "Le streaming RTSP ne sera pas disponible"
        return 1
    fi
    
    # Extract version using sed (more portable than grep -P)
    latest_version=$(echo "$api_response" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
    
    if [[ -z "$latest_version" ]]; then
        log_warning "Impossible de récupérer la version de MediaMTX"
        log_warning "Le streaming RTSP ne sera pas disponible"
        return 1
    fi
    
    log_info "Téléchargement de MediaMTX $latest_version pour $mediamtx_arch..."
    
    # MediaMTX release filename format: mediamtx_v1.x.x_linux_arm64v8.tar.gz
    local download_url="https://github.com/bluenviron/mediamtx/releases/download/${latest_version}/mediamtx_${latest_version}_linux_${mediamtx_arch}.tar.gz"
    local temp_dir
    temp_dir=$(mktemp -d)
    
    log_info "URL: $download_url"
    
    if ! curl -sSL "$download_url" -o "$temp_dir/mediamtx.tar.gz"; then
        log_warning "Échec du téléchargement de MediaMTX depuis $download_url"
        rm -rf "$temp_dir"
        return 1
    fi
    
    # Verify download
    if [[ ! -s "$temp_dir/mediamtx.tar.gz" ]]; then
        log_warning "Fichier téléchargé vide ou manquant"
        rm -rf "$temp_dir"
        return 1
    fi
    
    # Extract and install
    log_info "Extraction de MediaMTX..."
    if ! tar -xzf "$temp_dir/mediamtx.tar.gz" -C "$temp_dir" 2>&1; then
        log_warning "Échec de l'extraction de MediaMTX"
        rm -rf "$temp_dir"
        return 1
    fi
    
    # Check if binary exists
    if [[ ! -f "$temp_dir/mediamtx" ]]; then
        log_warning "Binaire mediamtx non trouvé dans l'archive"
        ls -la "$temp_dir/" 2>/dev/null || true
        rm -rf "$temp_dir"
        return 1
    fi
    
    # Install binary (use cp+chmod instead of install to avoid conflicts)
    log_info "Installation du binaire MediaMTX..."
    cp "$temp_dir/mediamtx" /usr/local/bin/mediamtx
    chmod 755 /usr/local/bin/mediamtx
    
    # Install default config if not exists
    if [[ ! -f /etc/mediamtx.yml ]]; then
        if [[ -f "$temp_dir/mediamtx.yml" ]]; then
            cp "$temp_dir/mediamtx.yml" /etc/mediamtx.yml
            chmod 644 /etc/mediamtx.yml
        else
            # Create minimal config for our use case
            cat > /etc/mediamtx.yml << 'MEDIAMTX_CONFIG'
# MediaMTX configuration for Motion Frontend
# Documentation: https://github.com/bluenviron/mediamtx

# Log level (debug, info, warn, error)
logLevel: info

# RTSP server settings
rtsp: yes
rtspAddress: :8554

# Disable other protocols we don't need
rtmp: no
hls: no
webrtc: no

# Path defaults - allow publishing from FFmpeg
pathDefaults:
  # Allow anyone to publish (FFmpeg will push streams here)
  publishUser:
  publishPass:
  # Allow anyone to read (clients will connect here)
  readUser:
  readPass:
MEDIAMTX_CONFIG
        fi
    fi
    
    # Create systemd service for MediaMTX
    cat > /etc/systemd/system/mediamtx.service << 'MEDIAMTX_SERVICE'
[Unit]
Description=MediaMTX RTSP Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mediamtx /etc/mediamtx.yml
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
MEDIAMTX_SERVICE
    
    # Enable and start the service
    systemctl daemon-reload
    systemctl enable mediamtx.service
    systemctl start mediamtx.service
    
    # Cleanup
    rm -rf "$temp_dir"
    
    # Verify installation
    if command -v mediamtx &> /dev/null; then
        log_success "MediaMTX installé avec succès"
        log_info "Service MediaMTX démarré sur le port 8554"
    else
        log_warning "L'installation de MediaMTX a échoué"
        return 1
    fi
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
    mkdir -p "$INSTALL_DIR/logs"  # Application logs directory
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
    
    # Create virtual environment with --system-site-packages
    # This allows access to system-installed packages like python3-opencv
    # which may not have a pip wheel for ARM architecture
    log_info "Création de l'environnement virtuel (avec accès aux packages système)..."
    python3 -m venv --system-site-packages "$VENV_DIR"
    
    # Upgrade pip
    log_info "Mise à jour de pip..."
    "$VENV_DIR/bin/pip" install --upgrade pip wheel setuptools
    
    # Install requirements
    if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
        log_info "Installation des dépendances Python..."
        # Use --ignore-installed for packages that may be system-installed
        "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" || {
            log_warning "Certains packages pip n'ont pas pu être installés"
            log_info "Tentative d'installation des packages manquants un par un..."
            while IFS= read -r pkg || [[ -n "$pkg" ]]; do
                # Skip comments and empty lines
                [[ "$pkg" =~ ^[[:space:]]*# ]] && continue
                [[ -z "${pkg// }" ]] && continue
                # Extract package name (without version specifier)
                pkg_name=$(echo "$pkg" | sed 's/[<>=!].*//' | tr -d '[:space:]')
                [[ -z "$pkg_name" ]] && continue
                "$VENV_DIR/bin/pip" install "$pkg" 2>/dev/null || \
                    log_warning "Package $pkg_name non installable via pip (peut être disponible via système)"
            done < "$INSTALL_DIR/requirements.txt"
        }
    else
        log_warning "Fichier requirements.txt non trouvé"
    fi
    
    # Verify OpenCV is available (either from pip or system)
    if "$VENV_DIR/bin/python" -c "import cv2; print(f'OpenCV {cv2.__version__} disponible')" 2>/dev/null; then
        log_success "OpenCV disponible dans l'environnement"
    else
        log_warning "OpenCV non disponible - MJPEG streaming sera désactivé"
        log_info "Pour installer OpenCV: sudo apt install python3-opencv"
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
        
        # Update Meeting configuration if provided
        if [[ -n "$MEETING_SERVER_URL" ]] || [[ -n "$MEETING_DEVICE_KEY" ]] || [[ -n "$MEETING_TOKEN_CODE" ]]; then
            log_info "Mise à jour de la configuration Meeting..."
            update_meeting_config "$app_config_dir/motion_frontend.json"
        fi
    else
        # Create minimal default configuration
        log_info "Création de la configuration par défaut..."
        
        # Escape values for JSON
        local meeting_server="${MEETING_SERVER_URL:-}"
        local meeting_key="${MEETING_DEVICE_KEY:-}"
        local meeting_token="${MEETING_TOKEN_CODE:-}"
        
        # Hostname defaults to devicekey in lowercase, or "motion-frontend" if not set
        local default_hostname="motion-frontend"
        if [[ -n "$meeting_key" ]]; then
            default_hostname=$(echo "$meeting_key" | tr '[:upper:]' '[:lower:]')
            log_info "Hostname défini à partir de la Device Key: $default_hostname"
        fi
        
        cat > "$app_config_dir/motion_frontend.json" << EOF
{
  "version": "1.0",
  "hostname": "${default_hostname}",
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
  ],
  "meeting": {
    "server_url": "${meeting_server}",
    "device_key": "${meeting_key}",
    "token_code": "${meeting_token}",
    "heartbeat_interval": 60
  }
}
EOF
    fi
    
    # Note: users.json is NOT created here - the UserManager will create it
    # automatically on first startup with properly hashed default passwords.
    # Default credentials: admin/admin (must change on first login)
    
    log_success "Configuration créée"
}

# Update Meeting config in existing JSON file
update_meeting_config() {
    local config_file="$1"
    local temp_file="${config_file}.tmp"
    
    # Check if python3 is available for JSON manipulation
    if command -v python3 &> /dev/null; then
        python3 << PYEOF
import json
import sys

try:
    with open('${config_file}', 'r') as f:
        config = json.load(f)
    
    # Ensure meeting section exists
    if 'meeting' not in config:
        config['meeting'] = {
            'server_url': '',
            'device_key': '',
            'token_code': '',
            'heartbeat_interval': 60
        }
    
    # Update values if provided
    server_url = '${MEETING_SERVER_URL}'
    device_key = '${MEETING_DEVICE_KEY}'
    token_code = '${MEETING_TOKEN_CODE}'
    
    if server_url:
        config['meeting']['server_url'] = server_url
    if device_key:
        config['meeting']['device_key'] = device_key
    if token_code:
        config['meeting']['token_code'] = token_code
    
    with open('${config_file}', 'w') as f:
        json.dump(config, f, indent=2)
    
    print('OK')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
PYEOF
    else
        log_warning "Python3 non disponible, configuration Meeting non mise à jour"
    fi
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
    chmod -R 755 "$INSTALL_DIR/logs"  # Ensure logs directory is writable
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
Environment="HOME=${INSTALL_DIR}"

ExecStart=${VENV_DIR}/bin/python -m backend.server \\
    --host ${DEFAULT_HOST} \\
    --port ${DEFAULT_PORT} \\
    --root ${INSTALL_DIR}

# Graceful shutdown: send SIGTERM, wait up to 15 seconds for clean exit
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=15

# Restart policy
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Security hardening (compatible with all systems)
NoNewPrivileges=true
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

update_systemd_service() {
    print_banner
    log_step "Mise à jour du service systemd"
    
    # Stop the service first
    log_info "Arrêt du service..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    sleep 2
    
    # Kill any remaining processes
    log_info "Nettoyage des processus résiduels..."
    pkill -9 -f "python.*backend.server" 2>/dev/null || true
    sleep 1
    
    # Check and free ports 8081-8090 (MJPEG ports range)
    for port in 8081 8082 8083 8084 8085 8086 8087 8088 8089 8090; do
        local pid
        pid=$(ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K\d+' | head -1)
        if [[ -n "$pid" ]]; then
            log_warning "Killing process $pid holding port $port"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
    sleep 1
    
    # Recreate the systemd service
    create_systemd_service
    
    # Restart the service
    log_info "Redémarrage du service..."
    systemctl start "$SERVICE_NAME"
    
    sleep 3
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service mis à jour et redémarré avec succès"
    else
        log_error "Le service n'a pas redémarré correctement"
        log_info "Vérifiez avec: journalctl -u $SERVICE_NAME -n 50"
    fi
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
    
    # Remove MediaMTX (optional)
    if command -v mediamtx &> /dev/null || [[ -f /etc/systemd/system/mediamtx.service ]]; then
        if confirm "Voulez-vous également désinstaller MediaMTX (serveur RTSP)?" "n"; then
            log_info "Arrêt et suppression de MediaMTX..."
            systemctl stop mediamtx.service 2>/dev/null || true
            systemctl disable mediamtx.service 2>/dev/null || true
            rm -f /etc/systemd/system/mediamtx.service
            rm -f /usr/local/bin/mediamtx
            rm -f /etc/mediamtx.yml
            systemctl daemon-reload
            log_success "MediaMTX désinstallé"
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
# Repair function
# ============================================================================

repair() {
    print_banner
    
    log_step "Réparation de Motion Frontend"
    
    local issues_found=0
    local issues_fixed=0
    local needs_reinstall=false
    
    echo ""
    echo -e "${CYAN}Vérification de l'intégrité de l'installation...${NC}"
    echo "─────────────────────────────────────────────────────────────────────"
    echo ""
    
    # ========================================================================
    # Check 1: Installation directory
    # ========================================================================
    log_info "Vérification du répertoire d'installation..."
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "✗ Répertoire d'installation absent: $INSTALL_DIR"
        needs_reinstall=true
        ((issues_found++)) || true
    else
        log_success "✓ Répertoire d'installation présent"
        
        # Check subdirectories
        local required_dirs=("backend" "static" "templates" "config" "logs")
        for dir in "${required_dirs[@]}"; do
            if [[ ! -d "$INSTALL_DIR/$dir" ]]; then
                log_warning "✗ Sous-répertoire manquant: $dir"
                ((issues_found++)) || true
                
                if [[ "$dir" == "logs" ]] || [[ "$dir" == "config" ]]; then
                    log_info "  → Création de $INSTALL_DIR/$dir"
                    mkdir -p "$INSTALL_DIR/$dir"
                    ((issues_fixed++)) || true
                else
                    needs_reinstall=true
                fi
            else
                log_success "✓ Sous-répertoire présent: $dir"
            fi
        done
    fi
    
    # ========================================================================
    # Check 2: Service user and groups
    # ========================================================================
    log_info "Vérification de l'utilisateur système..."
    
    if ! id "$SERVICE_USER" > /dev/null 2>&1; then
        log_warning "✗ Utilisateur '$SERVICE_USER' absent"
        ((issues_found++)) || true
        
        log_info "  → Création de l'utilisateur et des groupes..."
        create_user_and_groups
        ((issues_fixed++)) || true
    else
        log_success "✓ Utilisateur '$SERVICE_USER' présent"
        
        # Check group memberships
        local groups_to_check=(video audio gpio i2c spi)
        for grp in "${groups_to_check[@]}"; do
            if getent group "$grp" > /dev/null 2>&1; then
                if ! groups "$SERVICE_USER" 2>/dev/null | grep -qw "$grp"; then
                    log_warning "✗ Utilisateur non membre du groupe '$grp'"
                    ((issues_found++)) || true
                    
                    log_info "  → Ajout au groupe '$grp'..."
                    usermod -aG "$grp" "$SERVICE_USER"
                    ((issues_fixed++)) || true
                fi
            fi
        done
    fi
    
    # ========================================================================
    # Check 3: Python virtual environment
    # ========================================================================
    log_info "Vérification de l'environnement Python..."
    
    if [[ ! -d "$VENV_DIR" ]]; then
        log_warning "✗ Environnement virtuel absent"
        ((issues_found++)) || true
        
        if [[ -d "$INSTALL_DIR/backend" ]]; then
            log_info "  → Recréation de l'environnement virtuel..."
            setup_python_environment
            ((issues_fixed++)) || true
        else
            needs_reinstall=true
        fi
    elif [[ ! -f "$VENV_DIR/bin/python" ]]; then
        log_warning "✗ Python non trouvé dans l'environnement virtuel"
        ((issues_found++)) || true
        
        log_info "  → Recréation de l'environnement virtuel..."
        rm -rf "$VENV_DIR"
        setup_python_environment
        ((issues_fixed++)) || true
    else
        log_success "✓ Environnement Python présent"
        
        # Check if requirements are installed
        if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
            log_info "  Vérification des dépendances Python..."
            if ! "$VENV_DIR/bin/pip" check > /dev/null 2>&1; then
                log_warning "✗ Dépendances Python incomplètes"
                ((issues_found++)) || true
                
                log_info "  → Réinstallation des dépendances..."
                "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" > /dev/null 2>&1
                ((issues_fixed++)) || true
            else
                log_success "✓ Dépendances Python OK"
            fi
        fi
    fi
    
    # ========================================================================
    # Check 4: Systemd service
    # ========================================================================
    log_info "Vérification du service systemd..."
    
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    
    if [[ ! -f "$service_file" ]]; then
        log_warning "✗ Fichier service systemd absent"
        ((issues_found++)) || true
        
        if [[ -d "$INSTALL_DIR/backend" ]]; then
            log_info "  → Recréation du service systemd..."
            create_systemd_service
            ((issues_fixed++)) || true
        else
            needs_reinstall=true
        fi
    else
        log_success "✓ Service systemd présent"
        
        # Check if service has required shutdown options (KillMode, TimeoutStopSec)
        if ! grep -q "KillMode=mixed" "$service_file" 2>/dev/null || \
           ! grep -q "TimeoutStopSec=" "$service_file" 2>/dev/null; then
            log_warning "✗ Service systemd obsolète (options de shutdown manquantes)"
            ((issues_found++)) || true
            
            log_info "  → Mise à jour du service systemd..."
            # Stop service before updating
            systemctl stop "$SERVICE_NAME" 2>/dev/null || true
            sleep 2
            # Kill any remaining processes holding ports
            pkill -9 -f "python.*backend.server" 2>/dev/null || true
            sleep 1
            create_systemd_service
            ((issues_fixed++)) || true
        fi
        
        # Check if service is enabled
        if ! systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
            log_warning "✗ Service non activé au démarrage"
            ((issues_found++)) || true
            
            log_info "  → Activation du service..."
            systemctl enable "$SERVICE_NAME"
            ((issues_fixed++)) || true
        else
            log_success "✓ Service activé au démarrage"
        fi
    fi
    
    # ========================================================================
    # Check 5: Permissions
    # ========================================================================
    log_info "Vérification des permissions..."
    
    if [[ -d "$INSTALL_DIR" ]]; then
        local owner
        owner=$(stat -c '%U' "$INSTALL_DIR" 2>/dev/null)
        
        if [[ "$owner" != "$SERVICE_USER" ]]; then
            log_warning "✗ Propriétaire incorrect: $owner (attendu: $SERVICE_USER)"
            ((issues_found++)) || true
            
            log_info "  → Correction des permissions..."
            set_permissions
            ((issues_fixed++)) || true
        else
            log_success "✓ Permissions correctes"
        fi
    fi
    
    # ========================================================================
    # Check 6: MediaMTX (RTSP server)
    # ========================================================================
    log_info "Vérification de MediaMTX (serveur RTSP)..."
    
    if ! command -v mediamtx &> /dev/null; then
        log_warning "✗ MediaMTX non installé (streaming RTSP non disponible)"
        ((issues_found++)) || true
        
        log_info "  → Installation de MediaMTX..."
        if install_mediamtx; then
            if command -v mediamtx &> /dev/null; then
                ((issues_fixed++)) || true
            fi
        else
            log_warning "  → Échec de l'installation de MediaMTX (RTSP non disponible)"
        fi
    else
        log_success "✓ MediaMTX installé"
        
        # Check if service is running
        if ! systemctl is-active --quiet mediamtx 2>/dev/null; then
            log_warning "✗ Service MediaMTX non actif"
            ((issues_found++)) || true
            
            log_info "  → Démarrage du service MediaMTX..."
            systemctl start mediamtx 2>/dev/null || true
            ((issues_fixed++)) || true
        else
            log_success "✓ Service MediaMTX actif"
        fi
    fi
    
    # ========================================================================
    # Check 7: Configuration files
    # ========================================================================
    log_info "Vérification de la configuration..."
    
    local config_file="$INSTALL_DIR/config/motion_frontend.json"
    
    if [[ ! -f "$config_file" ]]; then
        log_warning "✗ Fichier de configuration absent"
        ((issues_found++)) || true
        
        log_info "  → Création de la configuration par défaut..."
        setup_configuration
        set_permissions
        ((issues_fixed++)) || true
    else
        log_success "✓ Fichier de configuration présent"
        
        # Check Meeting configuration (without burning token)
        check_meeting_config_repair
    fi
    
    # ========================================================================
    # Check 8: Log directory permissions
    # ========================================================================
    log_info "Vérification du répertoire de logs..."
    
    if [[ -d "$INSTALL_DIR/logs" ]]; then
        if [[ ! -w "$INSTALL_DIR/logs" ]] || [[ $(stat -c '%U' "$INSTALL_DIR/logs") != "$SERVICE_USER" ]]; then
            log_warning "✗ Permissions du répertoire logs incorrectes"
            ((issues_found++)) || true
            
            log_info "  → Correction des permissions logs..."
            chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/logs"
            chmod -R 755 "$INSTALL_DIR/logs"
            ((issues_fixed++)) || true
        else
            log_success "✓ Répertoire de logs OK"
        fi
    fi
    
    # ========================================================================
    # Summary and actions
    # ========================================================================
    echo ""
    echo "─────────────────────────────────────────────────────────────────────"
    echo ""
    
    if [[ "$needs_reinstall" == true ]]; then
        log_error "L'installation est trop endommagée pour être réparée."
        echo ""
        if confirm "Voulez-vous réinstaller Motion Frontend?" "y"; then
            echo ""
            # Preserve config if possible
            local backup_dir="/tmp/motion-frontend-config-backup-$(date +%Y%m%d%H%M%S)"
            if [[ -d "$INSTALL_DIR/config" ]]; then
                log_info "Sauvegarde de la configuration..."
                mkdir -p "$backup_dir"
                cp -r "$INSTALL_DIR/config"/* "$backup_dir/" 2>/dev/null || true
            fi
            
            # Clean and reinstall
            rm -rf "$INSTALL_DIR"
            SKIP_MEETING_CONFIG=true  # Don't ask for Meeting config, don't burn token
            install
            
            # Restore config
            if [[ -d "$backup_dir" ]]; then
                log_info "Restauration de la configuration..."
                cp -r "$backup_dir"/* "$INSTALL_DIR/config/"
                rm -rf "$backup_dir"
                set_permissions
            fi
        else
            log_info "Réparation annulée"
            exit 1
        fi
    elif [[ $issues_found -eq 0 ]]; then
        log_success "Aucun problème détecté - L'installation est saine"
    else
        echo -e "${CYAN}Résumé:${NC}"
        echo "  - Problèmes détectés: $issues_found"
        echo "  - Problèmes corrigés: $issues_fixed"
        
        if [[ $issues_fixed -gt 0 ]]; then
            echo ""
            log_success "Réparation terminée"
            
            # Restart service if it was running
            if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
                log_info "Redémarrage du service..."
                systemctl restart "$SERVICE_NAME"
            elif confirm "Voulez-vous démarrer le service?" "y"; then
                start_service
            fi
        fi
    fi
}

# Check Meeting config during repair (without burning token)
check_meeting_config_repair() {
    local config_file="$INSTALL_DIR/config/motion_frontend.json"
    
    if [[ ! -f "$config_file" ]]; then
        return
    fi
    
    # Extract meeting config using grep (works without jq)
    local device_key
    device_key=$(grep -o '"device_key"[[:space:]]*:[[:space:]]*"[^"]*"' "$config_file" 2>/dev/null | sed 's/.*:.*"\([^"]*\)"/\1/')
    
    if [[ -z "$device_key" ]]; then
        log_warning "✗ Configuration Meeting: Device Key absente"
        echo ""
        echo -e "${YELLOW}Le service Meeting n'est pas configuré.${NC}"
        
        if confirm "Voulez-vous configurer le service Meeting maintenant?" "n"; then
            # Configure Meeting but DON'T burn token during repair
            echo ""
            echo -e "${CYAN}Configuration Meeting (mode réparation - pas de consommation de token)${NC}"
            echo ""
            
            read -r -p "Device Key: " input_device_key
            if [[ -n "$input_device_key" ]]; then
                read -r -p "Token Code: " input_token
                
                if [[ -n "$input_token" ]]; then
                    # Validate credentials without burning token
                    log_info "Vérification des credentials (sans consommation de token)..."
                    
                    local api_url="${MEETING_SERVER_URL}/api/devices/${input_device_key}"
                    local response
                    response=$(curl -sSL -w "\n%{http_code}" "$api_url" 2>/dev/null)
                    
                    local http_code
                    http_code=$(echo "$response" | tail -n 1)
                    local body
                    body=$(echo "$response" | sed '$d')
                    
                    if [[ "$http_code" == "200" ]]; then
                        # Verify token matches
                        local stored_token
                        stored_token=$(echo "$body" | grep -o '"token_code"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:.*"\([^"]*\)"/\1/')
                        
                        if [[ "$stored_token" == "$input_token" ]]; then
                            log_success "✓ Credentials validés"
                            
                            # Update config file
                            MEETING_DEVICE_KEY="$input_device_key"
                            MEETING_TOKEN_CODE="$input_token"
                            update_meeting_config "$config_file"
                            
                            log_success "Configuration Meeting mise à jour"
                        else
                            log_error "✗ Token Code invalide"
                        fi
                    else
                        log_error "✗ Device Key non trouvée sur le serveur Meeting"
                    fi
                fi
            fi
        fi
    else
        log_success "✓ Configuration Meeting présente (Device Key: ${device_key:0:8}...)"
    fi
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
    
    # Configure and validate Meeting service
    if [[ "$SKIP_MEETING_CONFIG" != true ]]; then
        if [[ -n "$MEETING_DEVICE_KEY" ]] && [[ -n "$MEETING_TOKEN_CODE" ]]; then
            # Credentials provided via command line - validate them
            log_step "Validation des credentials Meeting"
            echo -e "${CYAN}Serveur Meeting: ${WHITE}${MEETING_SERVER_URL}${NC}"
            log_info "Device Key: ${MEETING_DEVICE_KEY}"
            log_info "Token Code: ${MEETING_TOKEN_CODE:0:3}***"
            echo ""
            
            if ! validate_meeting_credentials; then
                exit 1
            fi
            MEETING_VALIDATED=true
        else
            # Interactive configuration
            configure_meeting_service
        fi
    fi
    
    echo ""
    log_info "L'installation va commencer avec les paramètres suivants:"
    echo "  - Branche: $SELECTED_BRANCH"
    echo "  - Répertoire: $INSTALL_DIR"
    echo "  - Port: $DEFAULT_PORT"
    if [[ -n "$MEETING_DEVICE_KEY" ]] && [[ "$MEETING_VALIDATED" == true ]]; then
        echo "  - Meeting Device Key: ${MEETING_DEVICE_KEY:0:8}... ${GREEN}(validé)${NC}"
    elif [[ -n "$MEETING_DEVICE_KEY" ]]; then
        echo "  - Meeting Device Key: ${MEETING_DEVICE_KEY:0:8}..."
    fi
    echo ""
    
    if ! confirm "Continuer l'installation?" "y"; then
        log_info "Installation annulée"
        exit 0
    fi
    
    install_system_dependencies
    install_mediamtx
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
    echo "Options générales:"
    echo "  --help, -h              Affiche cette aide"
    echo "  --branch, -b            Affiche un menu pour choisir la branche à installer"
    echo "  --uninstall, -u         Désinstalle Motion Frontend"
    echo "  --update                Met à jour l'installation existante"
    echo "  --repair                Vérifie et répare l'installation"
    echo "  --update-service        Force la mise à jour du service systemd"
    echo ""
    echo "Configuration Meeting:"
    echo "  --device-key KEY        Device Key pour le service Meeting (obligatoire avec --token)"
    echo "  --token TOKEN           Token code pour le service Meeting (obligatoire avec --device-key)"
    echo "  --skip-meeting          Ne pas configurer le service Meeting"
    echo ""
    echo "  Note: Le serveur Meeting est fixé à ${MEETING_SERVER_URL}"
    echo "        La validation consume un token d'installation sur le serveur."
    echo ""
    echo "Exemples:"
    echo ""
    echo "  Installation rapide (branche main):"
    echo "    curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash"
    echo ""
    echo "  Installation avec choix de branche:"
    echo "    curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- --branch"
    echo ""
    echo "  Installation avec configuration Meeting:"
    echo "    curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- \\"
    echo "      --device-key YOUR_DEVICE_KEY --token YOUR_TOKEN"
    echo ""
    echo "  Installation sans Meeting:"
    echo "    curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- --skip-meeting"
    echo ""
    echo "  Mise à jour du service systemd:"
    echo "    sudo ./install_motion_frontend.sh --update-service"
    echo ""
    echo "  Réparation:"
    echo "    curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- --repair"
    echo ""
    echo "  Désinstallation:"
    echo "    curl -sSL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall"
    echo ""
}

# ============================================================================
# Main entry point
# ============================================================================

main() {
    local action="install"
    SELECT_BRANCH=false
    SKIP_MEETING_CONFIG=false
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
            --repair)
                action="repair"
                shift
                ;;
            --device-key)
                MEETING_DEVICE_KEY="$2"
                shift 2
                ;;
            --token)
                MEETING_TOKEN_CODE="$2"
                shift 2
                ;;
            --skip-meeting)
                SKIP_MEETING_CONFIG=true
                shift
                ;;
            --update-service)
                action="update-service"
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
        repair)
            check_root
            repair
            ;;
        update-service)
            check_root
            update_systemd_service
            ;;
    esac
}

# Run main function
main "$@"
