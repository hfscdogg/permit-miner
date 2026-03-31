<?php
/**
 * Plugin Name: Permit Miner
 * Description: Endpoints for Permit Miner lead-gen system: exclude, scan, registry.
 * Version: 1.0
 *
 * Deploy to: wp-content/mu-plugins/permit-miner.php
 *
 * Endpoints registered:
 *   GET /permit-exclude?pid=xxx&reason=existing_customer
 *   GET /permit-scan?pid=xxx
 *   POST /wp-json/permit-miner/v1/registry   (protected by X-Permit-Miner-Key header)
 *
 * Data files live at: wp-content/uploads/permit-miner/
 *   exclusions.json  — written by /permit-exclude, read by Tuesday send (GitHub Actions)
 *   scans.json       — written by /permit-scan, read by Monday pull (GitHub Actions)
 *
 * Registry is stored in wp_options (key: permit_miner_registry) so /permit-scan
 * can look up permit details instantly without a GitHub API call.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// ── Constants ─────────────────────────────────────────────────────────────────

define( 'PM_DATA_DIR', WP_CONTENT_DIR . '/uploads/permit-miner/' );
define( 'PM_EXCLUSIONS_FILE', PM_DATA_DIR . 'exclusions.json' );
define( 'PM_SCANS_FILE', PM_DATA_DIR . 'scans.json' );
define( 'PM_OPTIONS_KEY', 'permit_miner_registry' );

// Shared secret — must match PERMIT_MINER_API_KEY in GitHub Actions secrets
define( 'PM_API_KEY', defined( 'PERMIT_MINER_API_KEY' ) ? PERMIT_MINER_API_KEY : getenv( 'PERMIT_MINER_API_KEY' ) );

// Alert recipient — owner's email for scan alerts
define( 'PM_ALERT_EMAIL', 'henry@getlivewire.com' );

// ── Bootstrap ─────────────────────────────────────────────────────────────────

add_action( 'init', 'pm_register_endpoints' );
add_action( 'rest_api_init', 'pm_register_rest_routes' );

function pm_ensure_data_dir() {
    if ( ! file_exists( PM_DATA_DIR ) ) {
        wp_mkdir_p( PM_DATA_DIR );
        // Block direct browsing
        file_put_contents( PM_DATA_DIR . '.htaccess', "Order deny,allow\nDeny from all\n" );
    }
}


// ── Endpoint registration ──────────────────────────────────────────────────────

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


// ── /permit-exclude ───────────────────────────────────────────────────────────
// GET /permit-exclude?pid=xxx&reason=existing_customer
// One-click link from Monday preview email — no form, no auth needed.
// pid is a 16-char random ID, not guessable by outsiders.

function pm_handle_exclude() {
    $pid    = sanitize_text_field( $_GET['pid'] ?? '' );
    $reason = sanitize_text_field( $_GET['reason'] ?? 'unspecified' );

    // Validate reason
    $valid_reasons = [ 'existing_customer', 'not_homeowner', 'wrong_project', 'already_contacted' ];
    if ( ! in_array( $reason, $valid_reasons, true ) ) {
        $reason = 'unspecified';
    }

    if ( ! $pid ) {
        wp_die( 'Missing permit ID.', 'Permit Miner', [ 'response' => 400 ] );
    }

    pm_ensure_data_dir();

    // Append exclusion record
    $exclusions = pm_read_json( PM_EXCLUSIONS_FILE, [] );
    // Avoid duplicate entries for the same pid
    foreach ( $exclusions as $excl ) {
        if ( $excl['pid'] === $pid ) {
            pm_output_excluded_confirmation( $pid );
            return;
        }
    }
    $exclusions[] = [
        'pid'       => $pid,
        'reason'    => $reason,
        'timestamp' => gmdate( 'c' ),
    ];
    pm_write_json( PM_EXCLUSIONS_FILE, $exclusions );

    pm_output_excluded_confirmation( $pid );
}

function pm_output_excluded_confirmation( $pid ) {
    http_response_code( 200 );
    header( 'Content-Type: text/html; charset=utf-8' );
    echo '<!DOCTYPE html><html><head><meta charset="utf-8">'
       . '<title>Excluded — Permit Miner</title>'
       . '<style>body{font-family:Arial,sans-serif;padding:40px;color:#333;max-width:500px;margin:0 auto;}</style>'
       . '</head><body>'
       . '<h2 style="color:#1a2744;">Excluded</h2>'
       . '<p>This permit has been marked for exclusion. It will not receive a postcard on Tuesday.</p>'
       . '<p style="color:#999;font-size:12px;">You can close this tab.</p>'
       . '</body></html>';
    exit;
}


// ── /permit-scan ──────────────────────────────────────────────────────────────
// GET /permit-scan?pid=xxx
// Called by purl_script.js when homeowner lands on /welcome?pid=xxx.
// Returns JSON with permit_type for the page to use.

function pm_handle_scan() {
    $pid = sanitize_text_field( $_GET['pid'] ?? '' );

    if ( ! $pid ) {
        wp_send_json( [ 'status' => 'error', 'message' => 'Missing pid' ], 400 );
        return;
    }

    // Look up permit in registry (stored in wp_options by Tuesday send)
    $registry = get_option( PM_OPTIONS_KEY, [] );
    $permit   = $registry[ $pid ] ?? null;

    // Record the scan
    pm_ensure_data_dir();
    $scans = pm_read_json( PM_SCANS_FILE, [] );
    $already_scanned = false;
    foreach ( $scans as $scan ) {
        if ( $scan['pid'] === $pid ) {
            $already_scanned = true;
            break;
        }
    }

    // Always record scan timestamp for count tracking
    $scans[] = [
        'pid'       => $pid,
        'timestamp' => gmdate( 'c' ),
    ];
    pm_write_json( PM_SCANS_FILE, $scans );

    // Send alert email — only on first scan per pid
    if ( $permit && ! $already_scanned ) {
        pm_send_scan_alert( $pid, $permit );
    }

    // Return permit_type for purl_script.js to use
    wp_send_json( [
        'status'          => 'ok',
        'permit_type'     => $permit['permit_type'] ?? '',
        'is_new_construction' => $permit['is_new_construction'] ?? false,
    ] );
}

function pm_send_scan_alert( $pid, $permit ) {
    $owner   = esc_html( $permit['owner_name'] ?? 'Unknown Owner' );
    $phone   = esc_html( $permit['phone'] ?? '' );
    $address = esc_html( $permit['address'] ?? '' );
    $type    = esc_html( $permit['permit_type'] ?? '' );

    $phone_html = $phone
        ? '<a href="tel:' . esc_attr( $phone ) . '" style="color:#e8943a;font-size:24px;font-weight:bold;">' . $phone . '</a>'
        : '<em style="color:#999;">No phone on file</em>';

    $subject = "Permit Miner: QR scan — {$owner}";

    $body = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body '
          . 'style="font-family:Arial,sans-serif;color:#333;max-width:500px;margin:0 auto;">'
          . '<div style="background:#1a2744;padding:20px;color:#fff;">'
          . '<span style="color:#e8943a;font-size:18px;font-weight:bold;">PERMIT MINER</span>'
          . '<span style="float:right;font-size:12px;color:#aaa;">QR Scan Alert</span>'
          . '</div>'
          . '<div style="padding:24px;">'
          . '<h2 style="margin:0 0 8px;">' . $owner . '</h2>'
          . '<p style="color:#666;font-size:14px;margin:0 0 20px;">' . $address . '</p>'
          . '<p style="font-size:13px;color:#999;margin:0 0 8px;">Phone:</p>'
          . '<p style="margin:0 0 20px;">' . $phone_html . '</p>'
          . '<p style="font-size:12px;color:#999;">Permit type: ' . $type . '</p>'
          . '<p style="font-size:12px;color:#999;">PID: ' . esc_html( $pid ) . '</p>'
          . '</div>'
          . '</body></html>';

    wp_mail(
        PM_ALERT_EMAIL,
        $subject,
        $body,
        [ 'Content-Type: text/html; charset=UTF-8' ]
    );
}


// ── WP REST: POST /wp-json/permit-miner/v1/registry ──────────────────────────
// Called by Tuesday send to store permit registry in wp_options.
// Protected by X-Permit-Miner-Key header (shared secret).

function pm_register_rest_routes() {
    register_rest_route( 'permit-miner/v1', '/registry', [
        'methods'             => 'POST',
        'callback'            => 'pm_rest_update_registry',
        'permission_callback' => 'pm_rest_auth',
    ] );
}

function pm_rest_auth( WP_REST_Request $request ) {
    $key = $request->get_header( 'X-Permit-Miner-Key' );
    if ( ! PM_API_KEY ) {
        return new WP_Error( 'pm_no_key', 'API key not configured on server.', [ 'status' => 500 ] );
    }
    if ( ! hash_equals( PM_API_KEY, (string) $key ) ) {
        return new WP_Error( 'pm_auth_failed', 'Invalid API key.', [ 'status' => 401 ] );
    }
    return true;
}

function pm_rest_update_registry( WP_REST_Request $request ) {
    $registry = $request->get_json_params();
    if ( ! is_array( $registry ) ) {
        return new WP_Error( 'pm_bad_payload', 'Expected JSON object.', [ 'status' => 400 ] );
    }
    update_option( PM_OPTIONS_KEY, $registry, false );
    return rest_ensure_response( [
        'status' => 'ok',
        'count'  => count( $registry ),
    ] );
}


// ── JSON file helpers ─────────────────────────────────────────────────────────

function pm_read_json( $path, $default = [] ) {
    if ( ! file_exists( $path ) ) {
        return $default;
    }
    $content = file_get_contents( $path );
    $data    = json_decode( $content, true );
    return is_array( $data ) ? $data : $default;
}

function pm_write_json( $path, $data ) {
    file_put_contents( $path, json_encode( $data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE ) );
}
