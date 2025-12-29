#!/bin/bash
# File Version: 0.3.1
# Script de push de version device vers GitHub
# Crée une branche device-dev-{version} et la push vers le remote
# Repository: https://github.com/sn8k/Mme

set -uo pipefail

# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CHANGELOG_FILE="$PROJECT_ROOT/CHANGELOG.md"
REMOTE_NAME="${REMOTE_NAME:-origin}"
BRANCH_PREFIX="device-dev"

# GitHub repository
GITHUB_OWNER="sn8k"
GITHUB_REPO="Mme"
GITHUB_HTTPS_URL="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git"
GITHUB_SSH_URL="git@github.com:${GITHUB_OWNER}/${GITHUB_REPO}.git"

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# Fonctions utilitaires
# =============================================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# =============================================================================
# Extraction de la version
# =============================================================================
get_project_version() {
    if [[ ! -f "$CHANGELOG_FILE" ]]; then
        log_error "CHANGELOG.md non trouvé: $CHANGELOG_FILE"
        exit 1
    fi
    
    local version
    version=$(grep -m1 -E "^## [0-9]+\.[0-9]+\.[0-9]+" "$CHANGELOG_FILE" | sed -E "s/^## ([0-9]+\.[0-9]+\.[0-9]+[a-zA-Z]?).*/\1/")
    
    if [[ -z "$version" ]]; then
        log_error "Impossible d'extraire la version depuis le CHANGELOG"
        exit 1
    fi
    
    echo "$version"
}

# =============================================================================
# Vérifications et configuration Git
# =============================================================================
check_git_installed() {
    if ! command -v git &> /dev/null; then
        log_error "Git n'est pas installé"
        log_info "Installez Git avec: sudo apt install git"
        exit 1
    fi
}

configure_git_safe_directory() {
    # Ajouter le répertoire aux safe.directory pour éviter l'erreur "dubious ownership"
    if ! git config --global --get-all safe.directory 2>/dev/null | grep -q "^${PROJECT_ROOT}$"; then
        log_step "Ajout de $PROJECT_ROOT aux répertoires Git sûrs..."
        git config --global --add safe.directory "$PROJECT_ROOT"
        log_success "Répertoire ajouté aux safe.directory"
    fi
}

configure_git_user() {
    # Configurer l'utilisateur Git si non défini
    local git_user_name git_user_email
    
    git_user_name=$(git -C "$PROJECT_ROOT" config user.name 2>/dev/null || echo "")
    git_user_email=$(git -C "$PROJECT_ROOT" config user.email 2>/dev/null || echo "")
    
    if [[ -z "$git_user_name" ]]; then
        log_warning "Git user.name non configuré"
        read -p "Entrez votre nom (pour les commits Git) [Motion Frontend Device]: " input_name
        if [[ -n "$input_name" ]]; then
            git -C "$PROJECT_ROOT" config user.name "$input_name"
            log_success "user.name configuré: $input_name"
        else
            git -C "$PROJECT_ROOT" config user.name "Motion Frontend Device"
            log_info "user.name par défaut: Motion Frontend Device"
        fi
    fi
    
    if [[ -z "$git_user_email" ]]; then
        log_warning "Git user.email non configuré"
        local device_hostname
        device_hostname=$(hostname 2>/dev/null || echo "device")
        read -p "Entrez votre email (pour les commits Git) [${device_hostname}@motion-frontend.local]: " input_email
        if [[ -n "$input_email" ]]; then
            git -C "$PROJECT_ROOT" config user.email "$input_email"
            log_success "user.email configuré: $input_email"
        else
            git -C "$PROJECT_ROOT" config user.email "${device_hostname}@motion-frontend.local"
            log_info "user.email par défaut: ${device_hostname}@motion-frontend.local"
        fi
    fi
}

init_git_repo() {
    if git -C "$PROJECT_ROOT" rev-parse --git-dir > /dev/null 2>&1; then
        log_info "Dépôt Git existant détecté"
        return 0
    fi
    
    log_warning "Le répertoire n'est pas un dépôt Git"
    log_step "Initialisation du dépôt Git..."
    
    git -C "$PROJECT_ROOT" init
    log_success "Dépôt Git initialisé"
}

setup_remote() {
    local remote_url
    
    # Vérifier si le remote existe
    if git -C "$PROJECT_ROOT" remote get-url "$REMOTE_NAME" > /dev/null 2>&1; then
        remote_url=$(git -C "$PROJECT_ROOT" remote get-url "$REMOTE_NAME")
        log_info "Remote '$REMOTE_NAME' existant: $(echo "$remote_url" | sed 's/:.*@/:****@/')"
        return 0
    fi
    
    log_warning "Remote '$REMOTE_NAME' non configuré"
    log_step "Configuration du remote..."
    
    # Demander le type d'authentification
    echo ""
    echo "=== Configuration du remote GitHub ==="
    echo "Repository: https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}"
    echo ""
    echo "Choisissez le mode d'authentification:"
    echo "  1) HTTPS (avec token personnel)"
    echo "  2) SSH (avec clé SSH)"
    echo "  3) Afficher les instructions et quitter"
    echo ""
    read -p "Votre choix [1-3]: " auth_choice
    
    case "$auth_choice" in
        1)
            setup_https_auth
            ;;
        2)
            setup_ssh_auth
            ;;
        3)
            show_auth_instructions
            exit 0
            ;;
        *)
            log_error "Choix invalide"
            exit 1
            ;;
    esac
}

setup_https_auth() {
    echo ""
    log_step "Configuration HTTPS avec token personnel"
    echo ""
    echo "Vous avez besoin d'un Personal Access Token (PAT) GitHub."
    echo "Créez-en un sur: https://github.com/settings/tokens"
    echo "Permissions requises: repo (Full control)"
    echo ""
    
    read -p "Entrez votre nom d'utilisateur GitHub: " github_user
    read -sp "Entrez votre Personal Access Token: " github_token
    echo ""
    
    if [[ -z "$github_user" || -z "$github_token" ]]; then
        log_error "Nom d'utilisateur et token requis"
        exit 1
    fi
    
    # Configurer le remote avec le token
    local auth_url="https://${github_user}:${github_token}@github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git"
    git -C "$PROJECT_ROOT" remote add "$REMOTE_NAME" "$auth_url"
    
    # Configurer le credential helper pour ne pas redemander
    git -C "$PROJECT_ROOT" config credential.helper store
    
    log_success "Remote HTTPS configuré"
    log_info "Remote URL: https://${github_user}:****@github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git"
}

setup_ssh_auth() {
    echo ""
    log_step "Configuration SSH"
    
    # Déterminer le home directory de l'utilisateur réel (pas root si sudo)
    local real_home
    if [[ -n "${SUDO_USER:-}" ]]; then
        real_home=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    else
        real_home="$HOME"
    fi
    
    # Vérifier si une clé SSH existe
    local ssh_key=""
    for key_file in "$real_home/.ssh/id_ed25519.pub" "$real_home/.ssh/id_rsa.pub" "$real_home/.ssh/id_ecdsa.pub"; do
        if [[ -f "$key_file" ]]; then
            ssh_key="$key_file"
            break
        fi
    done
    
    if [[ -z "$ssh_key" ]]; then
        log_warning "Aucune clé SSH trouvée dans $real_home/.ssh/"
        echo ""
        read -p "Voulez-vous générer une nouvelle clé SSH? [o/N]: " generate_key
        
        if [[ "$generate_key" =~ ^[oOyY]$ ]]; then
            read -p "Entrez votre email GitHub: " github_email
            mkdir -p "$real_home/.ssh"
            ssh-keygen -t ed25519 -C "$github_email" -f "$real_home/.ssh/id_ed25519" -N ""
            # Corriger les permissions si exécuté avec sudo
            if [[ -n "${SUDO_USER:-}" ]]; then
                chown -R "$SUDO_USER:$SUDO_USER" "$real_home/.ssh"
            fi
            ssh_key="$real_home/.ssh/id_ed25519.pub"
            log_success "Clé SSH générée"
        else
            show_ssh_instructions
            exit 0
        fi
    fi
    
    echo ""
    log_info "Clé SSH publique trouvée: $ssh_key"
    echo ""
    echo "=== IMPORTANT ==="
    echo "Ajoutez cette clé publique à votre compte GitHub:"
    echo "https://github.com/settings/keys"
    echo ""
    echo "Votre clé publique:"
    echo "---"
    cat "$ssh_key"
    echo "---"
    echo ""
    read -p "Appuyez sur Entrée une fois la clé ajoutée sur GitHub..."
    
    # Configurer le remote SSH
    git -C "$PROJECT_ROOT" remote add "$REMOTE_NAME" "$GITHUB_SSH_URL"
    
    # Tester la connexion SSH (en tant qu'utilisateur réel si sudo)
    log_step "Test de la connexion SSH..."
    local ssh_test_result
    if [[ -n "${SUDO_USER:-}" ]]; then
        ssh_test_result=$(sudo -u "$SUDO_USER" ssh -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 || true)
    else
        ssh_test_result=$(ssh -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 || true)
    fi
    
    if echo "$ssh_test_result" | grep -qi "success"; then
        log_success "Connexion SSH réussie"
    else
        log_warning "Test SSH non concluant (peut être normal)"
    fi
    
    log_success "Remote SSH configuré: $GITHUB_SSH_URL"
}

show_auth_instructions() {
    echo ""
    echo "=============================================================================="
    echo "  INSTRUCTIONS DE CONFIGURATION GIT"
    echo "=============================================================================="
    echo ""
    echo "Repository: https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}"
    echo ""
    echo "--- OPTION 1: HTTPS avec Personal Access Token ---"
    echo ""
    echo "1. Créez un Personal Access Token sur GitHub:"
    echo "   https://github.com/settings/tokens/new"
    echo "   - Note: 'Motion Frontend Device'"
    echo "   - Expiration: selon vos besoins"
    echo "   - Scopes: cochez 'repo' (Full control)"
    echo ""
    echo "2. Configurez le dépôt:"
    echo "   cd $PROJECT_ROOT"
    echo "   sudo git config --global --add safe.directory $PROJECT_ROOT"
    echo "   sudo git init  # si pas encore fait"
    echo "   sudo git remote add origin https://USERNAME:TOKEN@github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git"
    echo ""
    echo "--- OPTION 2: SSH (recommandé) ---"
    echo ""
    echo "1. Générez une clé SSH (si pas déjà fait):"
    echo "   ssh-keygen -t ed25519 -C \"votre-email@example.com\""
    echo ""
    echo "2. Affichez votre clé publique:"
    echo "   cat ~/.ssh/id_ed25519.pub"
    echo ""
    echo "3. Ajoutez la clé sur GitHub:"
    echo "   https://github.com/settings/keys"
    echo ""
    echo "4. Configurez le dépôt:"
    echo "   cd $PROJECT_ROOT"
    echo "   sudo git config --global --add safe.directory $PROJECT_ROOT"
    echo "   sudo git init  # si pas encore fait"
    echo "   sudo git remote add origin ${GITHUB_SSH_URL}"
    echo ""
    echo "--- Après configuration ---"
    echo ""
    echo "Relancez ce script:"
    echo "   sudo $0"
    echo ""
    echo "=============================================================================="
}

show_ssh_instructions() {
    echo ""
    echo "=== Instructions SSH ==="
    echo ""
    echo "1. Générez une clé SSH:"
    echo "   ssh-keygen -t ed25519 -C \"votre-email@example.com\""
    echo ""
    echo "2. Affichez et copiez votre clé publique:"
    echo "   cat ~/.ssh/id_ed25519.pub"
    echo ""
    echo "3. Ajoutez-la sur GitHub: https://github.com/settings/keys"
    echo ""
    echo "4. Relancez ce script"
    echo ""
}

check_uncommitted_changes() {
    if ! git -C "$PROJECT_ROOT" diff-index --quiet HEAD -- 2>/dev/null; then
        return 1
    fi
    return 0
}

get_device_hostname() {
    hostname 2>/dev/null || echo "unknown"
}

ensure_initial_commit() {
    # Vérifier s'il y a au moins un commit
    if git -C "$PROJECT_ROOT" rev-parse HEAD > /dev/null 2>&1; then
        log_info "Commits existants détectés"
        return 0
    fi
    
    log_warning "Aucun commit dans le dépôt"
    log_step "Création du commit initial..."
    
    git -C "$PROJECT_ROOT" add -A
    git -C "$PROJECT_ROOT" commit -m "Initial commit - Motion Frontend v$(get_project_version)"
    
    log_success "Commit initial créé"
}

# =============================================================================
# Fonction principale
# =============================================================================
main() {
    local force_push=false
    local include_uncommitted=false
    local custom_message=""
    local dry_run=false
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--force)
                force_push=true
                shift
                ;;
            -u|--uncommitted)
                include_uncommitted=true
                shift
                ;;
            -m|--message)
                custom_message="$2"
                shift 2
                ;;
            -d|--dry-run)
                dry_run=true
                shift
                ;;
            -r|--remote)
                REMOTE_NAME="$2"
                shift 2
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Pousse la version actuelle de Motion Frontend vers GitHub"
                echo "en créant une branche device-dev-{version}"
                echo ""
                echo "Repository: https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}"
                echo ""
                echo "Options:"
                echo "  -f, --force         Force le push (écrase la branche distante si elle existe)"
                echo "  -u, --uncommitted   Inclut les changements non commités (crée un commit)"
                echo "  -m, --message MSG   Message de commit personnalisé (avec -u)"
                echo "  -d, --dry-run       Affiche ce qui serait fait sans exécuter"
                echo "  -r, --remote NAME   Nom du remote (défaut: origin)"
                echo "  -h, --help          Affiche cette aide"
                echo ""
                echo "Exemples:"
                echo "  sudo $0                           # Push la version actuelle"
                echo "  sudo $0 -f                        # Force push"
                echo "  sudo $0 -u -m 'WIP: test caméra' # Inclut les changements non commités"
                echo "  sudo $0 -d                        # Simulation (dry-run)"
                exit 0
                ;;
            *)
                log_error "Option inconnue: $1"
                echo "Utilisez --help pour l'aide"
                exit 1
                ;;
        esac
    done

    cd "$PROJECT_ROOT"
    
    echo ""
    log_info "=== Push Device Version vers GitHub ==="
    log_info "Repository: https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}"
    log_info "Répertoire projet: $PROJECT_ROOT"
    echo ""
    
    # Vérifications et configuration
    check_git_installed
    configure_git_safe_directory
    init_git_repo
    configure_git_user
    setup_remote
    ensure_initial_commit
    
    # Récupération de la version
    local version
    version=$(get_project_version)
    log_info "Version détectée: $version"
    
    # Récupération du hostname du device
    local device_name
    device_name=$(get_device_hostname)
    log_info "Device: $device_name"
    
    # Construction du nom de branche
    local branch_name="${BRANCH_PREFIX}-${version}"
    log_info "Branche cible: $branch_name"
    
    # Vérification des changements non commités
    if ! check_uncommitted_changes; then
        if [[ "$include_uncommitted" == true ]]; then
            log_warning "Changements non commités détectés - seront inclus"
        else
            log_warning "Changements non commités détectés"
            log_info "Utilisez -u pour les inclure ou commitez-les d'abord"
            git -C "$PROJECT_ROOT" status --short
            echo ""
        fi
    fi
    
    # Mode dry-run
    if [[ "$dry_run" == true ]]; then
        echo ""
        log_info "[DRY-RUN] Actions qui seraient effectuées:"
        echo "  1. Création/checkout de la branche: $branch_name"
        if [[ "$include_uncommitted" == true ]] && ! check_uncommitted_changes; then
            echo "  2. Commit des changements non commités"
        fi
        echo "  3. Push vers $REMOTE_NAME/$branch_name"
        if [[ "$force_push" == true ]]; then
            echo "     (avec --force)"
        fi
        exit 0
    fi
    
    # Sauvegarde de la branche actuelle
    local current_branch
    current_branch=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
    log_info "Branche actuelle: $current_branch"
    
    # Création ou checkout de la branche device-dev
    if git -C "$PROJECT_ROOT" show-ref --verify --quiet "refs/heads/$branch_name"; then
        log_info "La branche $branch_name existe déjà localement"
        git -C "$PROJECT_ROOT" checkout "$branch_name"
    else
        log_step "Création de la branche $branch_name"
        git -C "$PROJECT_ROOT" checkout -b "$branch_name"
    fi
    
    # Gestion des changements non commités
    if [[ "$include_uncommitted" == true ]] && ! check_uncommitted_changes; then
        local commit_msg="${custom_message:-[Device: $device_name] WIP - v$version}"
        log_step "Commit des changements: $commit_msg"
        git -C "$PROJECT_ROOT" add -A
        git -C "$PROJECT_ROOT" commit -m "$commit_msg"
    fi
    
    # Push vers le remote
    log_step "Push vers $REMOTE_NAME/$branch_name..."
    local push_cmd="git -C \"$PROJECT_ROOT\" push"
    if [[ "$force_push" == true ]]; then
        push_cmd="$push_cmd --force"
    fi
    push_cmd="$push_cmd \"$REMOTE_NAME\" \"$branch_name\""
    
    if eval "$push_cmd"; then
        log_success "Push réussi!"
        
        echo ""
        echo "=== Résumé ==="
        echo "  Version:       $version"
        echo "  Device:        $device_name"
        echo "  Branche:       $branch_name"
        echo "  Remote:        $REMOTE_NAME"
        echo "  Date:          $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""
        echo "  URL GitHub:    https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/tree/$branch_name"
        echo ""
    else
        log_error "Échec du push"
        log_info "Vérifiez votre authentification GitHub"
        # Retour à la branche d'origine en cas d'erreur
        git -C "$PROJECT_ROOT" checkout "$current_branch" 2>/dev/null || true
        exit 1
    fi
    
    # Option pour revenir à la branche d'origine
    if [[ "$current_branch" != "$branch_name" ]]; then
        log_info "Retour à la branche d'origine: $current_branch"
        git -C "$PROJECT_ROOT" checkout "$current_branch"
    fi
    
    log_success "Opération terminée avec succès!"
}

# Point d'entrée
main "$@"
