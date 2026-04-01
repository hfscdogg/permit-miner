<?php
/**
 * Plugin Name: Permit Miner
 * Description: Stateless inbound endpoints for the Permit Miner lead-gen system.
 * Version: 2.0
 *
 * Deploy to: wp-content/mu-plugins/permit-miner.php
 *
 * Endpoints:
 *   GET /permit-exclude?pid=xxx&reason=existing_customer&sig=yyy
 *   GET /permit-scan?pid=xxx&sig=yyy
 *
 * This plugin validates inbound requests and returns minimal responses.
 * No local files, no wp_options, no email, no outbound API calls.
 * All state lives in the Python pipeline's SQLite database.
 *
 * Required wp-config.php constant:
 *   PERMIT_MINER_HMAC_SECRET — shared secret for signing pid URLs
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// ── Config (from wp-config.php) ─────────────────────────────────────────────

define( 'PM_HMAC_SECRET', defined( 'PERMIT_MINER_HMAC_SECRET' ) ? PERMIT_MINER_HMAC_SECRET : '' );

// Rate limit: max requests per IP within the window (seconds)
define( 'PM_RATE_LIMIT_MAX',    30 );
define( 'PM_RATE_LIMIT_WINDOW', 300 );  // 5 minutes

// Permit ID format: exactly 16 lowercase hex characters
define( 'PM_PID_PATTERN', '/^[a-f0-9]{16}$/' );


// ── Bootstrap ────────────────────────────────────────────────────────────────

add_action( 'init', 'pm_register_endpoints' );


// ── Endpoint registration ────────────────────────────────────────────────────

function pm_register_endpoints() {
    add_rewrite_rule( '^permit-exclude/?$', 'index.php?pm_action=exclude', 'top' );
    add_rewrite_rule( '^permit-scan/?$',    'index.php?pm_action=scan',    'top' );
    add_rewrite_tag( '%pm_action%', '([^&]+)' );
}

add_action( 'template_redirect', 'pm_handle_request' );

function pm_handle_request() {
    $action = get_query_var( 'pm_action' );
    if ( ! $action ) {
        return;
    }
    switch ( $action ) {
        case 'exclude':
            pm_handle_exclude();
            break;
        case 'scan':
            pm_handle_scan();
            break;
    }
    exit;
}


// ── Shared validation ────────────────────────────────────────────────────────

/**
 * Validate permit ID format (16 lowercase hex chars).
 */
function pm_validate_pid( string $pid ): bool {
    return (bool) preg_match( PM_PID_PATTERN, $pid );
}

/**
 * Verify HMAC-SHA256 signature: sig = hmac_sha256(secret, pid).
 */
function pm_verify_signature( string $pid, string $sig ): bool {
    if ( ! PM_HMAC_SECRET ) {
        return false;
    }
    $expected = hash_hmac( 'sha256', $pid, PM_HMAC_SECRET );
    return hash_equals( $expected, $sig );
}

/**
 * IP-based rate limiter using WordPress transients.
 * Returns true if the request is within limits, false if blocked.
 */
function pm_check_rate_limit(): bool {
    $ip  = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
    $key = 'pm_rl_' . md5( $ip );

    $count = (int) get_transient( $key );
    if ( $count >= PM_RATE_LIMIT_MAX ) {
        return false;
    }

    set_transient( $key, $count + 1, PM_RATE_LIMIT_WINDOW );
    return true;
}

/**
 * Run all common validation checks. Returns validated pid or exits with error.
 */
function pm_validate_request(): string {
    // Rate limit
    if ( ! pm_check_rate_limit() ) {
        http_response_code( 429 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Rate limit exceeded' ] );
        exit;
    }

    $pid = sanitize_text_field( $_GET['pid'] ?? '' );
    $sig = sanitize_text_field( $_GET['sig'] ?? '' );

    // Require pid
    if ( ! $pid ) {
        http_response_code( 400 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Missing pid' ] );
        exit;
    }

    // Strict format check
    if ( ! pm_validate_pid( $pid ) ) {
        http_response_code( 400 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Invalid pid format' ] );
        exit;
    }

    // Signature verification
    if ( ! pm_verify_signature( $pid, $sig ) ) {
        http_response_code( 403 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Invalid signature' ] );
        exit;
    }

    return $pid;
}


// ── /permit-exclude ──────────────────────────────────────────────────────────
// GET /permit-exclude?pid=xxx&reason=existing_customer&sig=yyy

function pm_handle_exclude() {
    $pid    = pm_validate_request();
    $reason = sanitize_text_field( $_GET['reason'] ?? 'unspecified' );

    $valid_reasons = [ 'existing_customer', 'not_homeowner', 'wrong_project', 'already_contacted' ];
    if ( ! in_array( $reason, $valid_reasons, true ) ) {
        $reason = 'unspecified';
    }

    // Return branded confirmation page
    http_response_code( 200 );
    header( 'Content-Type: text/html; charset=utf-8' );
    echo '<!DOCTYPE html><html><head><meta charset="utf-8">'
       . '<title>Excluded</title>'
       . '<style>body{font-family:Arial,sans-serif;padding:40px;color:#333;max-width:500px;margin:0 auto;}</style>'
       . '</head><body>'
       . '<h2 style="color:#1a2744;">Excluded</h2>'
       . '<p>This permit has been marked for exclusion. It will not receive a postcard on Tuesday.</p>'
       . '<p style="color:#999;font-size:12px;">You can close this tab.</p>'
       . '</body></html>';
    exit;
}


// ── /permit-scan ─────────────────────────────────────────────────────────────
// GET /permit-scan?pid=xxx&sig=yyy

function pm_handle_scan() {
    $pid = pm_validate_request();

    // Validated successfully -- return minimal acknowledgment
    wp_send_json( [
        'status' => 'ok',
    ] );
}
