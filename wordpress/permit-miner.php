<?php
/**
 * Plugin Name: Permit Miner
 * Description: Inbound endpoints for the Permit Miner lead-gen system.
 * Version: 2.2
 *
 * Deploy to: wp-content/mu-plugins/permit-miner.php
 *
 * Endpoints:
 *   GET  /permit-exclude?pid=xxx&reason=existing_customer&sig=yyy
 *   GET  /permit-scan?pid=xxx&sig=yyy
 *   POST /permit-registry  (header: X-Permit-Miner-Auth: <secret>)
 *
 * Exclusions are written to a JSON file that the Tuesday pipeline fetches.
 * Scans are written to a JSON file that the Monday pipeline reads.
 * Registry data is POSTed here by the pipeline after each Monday/Tuesday run
 * and cached locally; the scan endpoint reads it to personalize PURL content.
 *
 * Required wp-config.php constant:
 *   PERMIT_MINER_HMAC_SECRET — shared secret for signing pid URLs and
 *                              authenticating registry uploads
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// ── Config (from wp-config.php) ─────────────────────────────────────────────

define( 'PM_HMAC_SECRET', defined( 'PERMIT_MINER_HMAC_SECRET' ) ? PERMIT_MINER_HMAC_SECRET : '' );

// Data directory for exclusion/scan JSON files
define( 'PM_DATA_DIR', WP_CONTENT_DIR . '/uploads/permit-miner/' );

// Rate limit: max requests per IP within the window (seconds)
define( 'PM_RATE_LIMIT_MAX',    30 );
define( 'PM_RATE_LIMIT_WINDOW', 300 );  // 5 minutes

// Permit ID format: exactly 16 lowercase hex characters
define( 'PM_PID_PATTERN', '/^[a-f0-9]{16}$/' );


// ── Bootstrap ────────────────────────────────────────────────────────────────

add_action( 'init', 'pm_register_endpoints' );


// ── Endpoint registration ────────────────────────────────────────────────────

function pm_register_endpoints() {
    add_rewrite_rule( '^permit-exclude/?$',  'index.php?pm_action=exclude',  'top' );
    add_rewrite_rule( '^permit-scan/?$',     'index.php?pm_action=scan',     'top' );
    add_rewrite_rule( '^permit-registry/?$', 'index.php?pm_action=registry', 'top' );
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
        case 'registry':
            pm_handle_registry_upload();
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


// ── Data file helpers ────────────────────────────────────────────────────────

/**
 * Ensure data directory exists.
 */
function pm_ensure_data_dir() {
    if ( ! file_exists( PM_DATA_DIR ) ) {
        wp_mkdir_p( PM_DATA_DIR );
    }
}

/**
 * Append a JSON record to a file (one JSON array per file).
 */
function pm_append_json( string $filename, array $record ) {
    pm_ensure_data_dir();
    $path = PM_DATA_DIR . $filename;

    $data = [];
    if ( file_exists( $path ) ) {
        $contents = file_get_contents( $path );
        $decoded  = json_decode( $contents, true );
        if ( is_array( $decoded ) ) {
            $data = $decoded;
        }
    }

    $data[] = $record;
    file_put_contents( $path, json_encode( $data, JSON_PRETTY_PRINT ), LOCK_EX );
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

    // Write exclusion to JSON file for Tuesday pipeline to pick up
    pm_append_json( 'exclusions.json', [
        'pid'       => $pid,
        'reason'    => $reason,
        'timestamp' => gmdate( 'c' ),
    ] );

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

    // Write scan event to JSON file for Monday pipeline to pick up
    pm_append_json( 'scans.json', [
        'pid'       => $pid,
        'timestamp' => gmdate( 'c' ),
    ] );

    // Look up the permit so the PURL JS can personalize the landing page.
    // Missing entries (permit hasn't shipped yet, or registry not synced)
    // degrade to the default landing page content — not an error.
    $permit = pm_lookup_permit( $pid );

    $response = [ 'status' => 'ok' ];
    if ( $permit ) {
        $response['permit_type']         = (string) ( $permit['permit_type'] ?? '' );
        $response['permit_tags']         = $permit['permit_tags'] ?? [];
        $response['segment']             = (string) ( $permit['segment'] ?? '' );
        $response['is_new_construction'] = (bool)   ( $permit['is_new_construction'] ?? false );
    }
    wp_send_json( $response );
}


// ── /permit-registry (upload) ────────────────────────────────────────────────
// POST /permit-registry
// Header: X-Permit-Miner-Auth: <PERMIT_MINER_HMAC_SECRET>
// Body: JSON object keyed by permit id

function pm_handle_registry_upload() {
    if ( ( $_SERVER['REQUEST_METHOD'] ?? 'GET' ) !== 'POST' ) {
        http_response_code( 405 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'POST required' ] );
        exit;
    }

    if ( ! PM_HMAC_SECRET ) {
        http_response_code( 500 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Server missing secret' ] );
        exit;
    }

    $provided = $_SERVER['HTTP_X_PERMIT_MINER_AUTH'] ?? '';
    if ( ! $provided || ! hash_equals( PM_HMAC_SECRET, $provided ) ) {
        http_response_code( 403 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Invalid auth' ] );
        exit;
    }

    $body    = file_get_contents( 'php://input' );
    $decoded = json_decode( $body, true );
    if ( ! is_array( $decoded ) ) {
        http_response_code( 400 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Invalid JSON body' ] );
        exit;
    }

    pm_ensure_data_dir();
    $path = PM_DATA_DIR . 'permit_registry.json';
    $tmp  = $path . '.tmp';
    if ( file_put_contents( $tmp, json_encode( $decoded ), LOCK_EX ) === false
         || ! rename( $tmp, $path ) ) {
        http_response_code( 500 );
        header( 'Content-Type: application/json; charset=utf-8' );
        echo json_encode( [ 'status' => 'error', 'message' => 'Write failed' ] );
        exit;
    }

    wp_send_json( [ 'status' => 'ok', 'count' => count( $decoded ) ] );
}


// ── Registry lookup helper ───────────────────────────────────────────────────

function pm_lookup_permit( string $pid ) {
    $path = PM_DATA_DIR . 'permit_registry.json';
    if ( ! file_exists( $path ) ) {
        return null;
    }
    $raw = file_get_contents( $path );
    if ( ! $raw ) {
        return null;
    }
    $registry = json_decode( $raw, true );
    if ( ! is_array( $registry ) ) {
        return null;
    }
    return $registry[ $pid ] ?? null;
}
