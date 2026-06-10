#!/usr/bin/env bash
# reset-site.sh - Complete reset of Daily Paper Report site data
#
# This script clears ALL data from:
# 1. GitHub state branch (state.sqlite and archives)
# 2. GitHub Pages deployment (deployed site content)
# 3. Local public/ directory
#
# Usage:
#   ./scripts/reset-site.sh              # Interactive mode
#   ./scripts/reset-site.sh --confirm    # Skip confirmation prompt
#   ./scripts/reset-site.sh --dry-run    # Show what would be done without executing

set -euo pipefail

# Configuration
REPO="DennySORA/Daily-Paper-Report"
STATE_BRANCH="state"
OUTPUT_DIR="public"
SITE_URL="https://paper.sorahane-kyoukai.org"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
DRY_RUN=false
CONFIRMED=false
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            ;;
        --confirm)
            CONFIRMED=true
            ;;
        --help|-h)
            echo "Usage: $0 [--confirm] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --confirm    Skip confirmation prompt"
            echo "  --dry-run    Show what would be done without executing"
            echo ""
            echo "This script completely resets the Daily Paper Report site by:"
            echo "  1. Deleting the state branch (state.sqlite + archives)"
            echo "  2. Clearing local public/ directory (keeping CNAME)"
            echo "  3. Triggering reset-site workflow to deploy empty site"
            exit 0
            ;;
    esac
done

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} Would execute: $*"
    else
        "$@"
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed. Please install it first."
        exit 1
    fi

    if ! gh auth status &> /dev/null; then
        log_error "GitHub CLI is not authenticated. Run 'gh auth login' first."
        exit 1
    fi

    log_success "Prerequisites OK"
}

# Show current state
show_current_state() {
    echo ""
    log_info "=== Current State ==="

    # Check state branch
    if gh api "repos/${REPO}/branches/${STATE_BRANCH}" &> /dev/null; then
        log_info "State branch: EXISTS"
    else
        log_info "State branch: NOT FOUND"
    fi

    # Check deployed site
    if curl -sf "${SITE_URL}/api/daily.json" > /dev/null 2>&1; then
        PAPER_COUNT=$(curl -sf "${SITE_URL}/api/daily.json" | jq '.papers | length' 2>/dev/null || echo "unknown")
        ARCHIVE_COUNT=$(curl -sf "${SITE_URL}/api/daily.json" | jq '.archive_dates | length' 2>/dev/null || echo "unknown")
        log_info "Deployed site: ACTIVE (${PAPER_COUNT} papers, ${ARCHIVE_COUNT} archive dates)"
    else
        log_info "Deployed site: EMPTY or ERROR"
    fi

    # Check local public directory
    if [ -d "${OUTPUT_DIR}" ]; then
        LOCAL_FILES=$(find "${OUTPUT_DIR}" -type f ! -name "CNAME" 2>/dev/null | wc -l | tr -d ' ')
        log_info "Local public/: ${LOCAL_FILES} files (excluding CNAME)"
    else
        log_info "Local public/: NOT FOUND"
    fi

    # Check running workflows
    RUNNING=$(gh run list --repo "${REPO}" --status in_progress --json databaseId --jq 'length' 2>/dev/null || echo "0")
    QUEUED=$(gh run list --repo "${REPO}" --status queued --json databaseId --jq 'length' 2>/dev/null || echo "0")
    if [ "$RUNNING" != "0" ] || [ "$QUEUED" != "0" ]; then
        log_warn "Running workflows: ${RUNNING}, Queued: ${QUEUED}"
    fi

    echo ""
}

# Confirmation prompt
confirm_reset() {
    if [ "$CONFIRMED" = true ]; then
        return 0
    fi

    echo -e "${RED}WARNING: This will permanently delete ALL site data!${NC}"
    echo ""
    echo "The following will be deleted:"
    echo "  - State branch (state.sqlite, all historical archives)"
    echo "  - All deployed content on GitHub Pages"
    echo "  - All local files in public/ (except CNAME)"
    echo ""
    read -p "Type 'RESET' to confirm: " CONFIRM

    if [ "$CONFIRM" != "RESET" ]; then
        log_error "Reset cancelled."
        exit 1
    fi
}

# Cancel running workflows
cancel_workflows() {
    log_info "Cancelling running workflows..."

    # Get running and queued workflow IDs
    WORKFLOW_IDS=$(gh run list --repo "${REPO}" --status in_progress --status queued --json databaseId --jq '.[].databaseId' 2>/dev/null || true)

    if [ -z "$WORKFLOW_IDS" ]; then
        log_success "No running workflows to cancel"
        return 0
    fi

    for ID in $WORKFLOW_IDS; do
        run_cmd gh run cancel "$ID" --repo "${REPO}" 2>/dev/null || true
        log_info "Cancelled workflow: $ID"
    done

    # Wait for cancellation
    if [ "$DRY_RUN" = false ]; then
        sleep 5
    fi

    log_success "Workflows cancelled"
}

# Delete state branch
delete_state_branch() {
    log_info "Deleting state branch..."

    if gh api "repos/${REPO}/branches/${STATE_BRANCH}" &> /dev/null; then
        run_cmd gh api -X DELETE "repos/${REPO}/git/refs/heads/${STATE_BRANCH}"
        log_success "State branch deleted"
    else
        log_info "State branch already deleted"
    fi
}

# Clear local public directory
clear_local_public() {
    log_info "Clearing local public/ directory..."

    if [ -d "${OUTPUT_DIR}" ]; then
        # Remove everything except CNAME
        find "${OUTPUT_DIR}" -mindepth 1 ! -name "CNAME" -exec rm -rf {} + 2>/dev/null || true
        log_success "Local public/ cleared (CNAME preserved)"
    else
        log_info "Local public/ does not exist"
    fi
}

# Clear local state.sqlite
clear_local_state() {
    log_info "Clearing local state.sqlite..."

    if [ -f "state.sqlite" ]; then
        run_cmd rm -f state.sqlite
        log_success "Local state.sqlite deleted"
    else
        log_info "No local state.sqlite found"
    fi
}

# Trigger clean deployment
trigger_clean_deploy() {
    log_info "Triggering reset-site workflow..."

    run_cmd gh workflow run reset-site.yaml \
        --repo "${REPO}" \
        --ref main \
        -f confirm_reset=RESET

    log_success "Reset workflow triggered"

    if [ "$DRY_RUN" = false ]; then
        echo ""
        log_info "Waiting for workflow to start..."
        sleep 10

        # Get the latest workflow run
        LATEST_RUN=$(gh run list --repo "${REPO}" --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || echo "")

        if [ -n "$LATEST_RUN" ]; then
            log_info "Workflow started: https://github.com/${REPO}/actions/runs/${LATEST_RUN}"
            echo ""
            log_info "Monitor with: gh run watch ${LATEST_RUN}"
        fi
    fi
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  Daily Paper Report - Site Reset Script"
    echo "=========================================="
    echo ""

    check_prerequisites
    show_current_state
    confirm_reset

    echo ""
    log_info "=== Starting Reset ==="
    echo ""

    cancel_workflows
    delete_state_branch
    clear_local_public
    clear_local_state
    trigger_clean_deploy

    echo ""
    log_success "=========================================="
    log_success "  Reset complete!"
    log_success "=========================================="
    echo ""
    log_info "The site will be empty after the workflow completes."
    log_info "To regenerate one day of data, run:"
    echo ""
    echo "  gh workflow run daily-digest.yaml --ref main -f target_date=2026-03-05"
    echo ""
}

main
