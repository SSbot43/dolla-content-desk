<?php
/**
 * Plugin Name: Keys-Shop Content OS Bridge
 * Description: Secure signed bridge for the local Keys-Shop Content Desk: product/category search, media upload and WordPress publishing.
 * Version: 0.1.0
 * Author: Keys-Shop
 */

if (!defined('ABSPATH')) { exit; }

const KEYS_CONTENT_OS_VERSION = '0.1.0';
const KEYS_CONTENT_OS_SECRET_OPTION = 'keys_content_os_bridge_secret';

function keys_content_os_secret() {
    $secret = get_option(KEYS_CONTENT_OS_SECRET_OPTION, '');
    if (!$secret) {
        try {
            $secret = bin2hex(random_bytes(32));
        } catch (Exception $e) {
            $secret = wp_generate_password(64, true, true);
        }
        update_option(KEYS_CONTENT_OS_SECRET_OPTION, $secret, false);
    }
    return (string) $secret;
}

register_activation_hook(__FILE__, 'keys_content_os_secret');

function keys_content_os_query_string(WP_REST_Request $request) {
    $params = $request->get_query_params();
    ksort($params);
    return http_build_query($params, '', '&', PHP_QUERY_RFC3986);
}

function keys_content_os_permission(WP_REST_Request $request) {
    $secret = keys_content_os_secret();
    $timestamp = trim((string) $request->get_header('x-content-desk-timestamp'));
    $signature = trim((string) $request->get_header('x-content-desk-signature'));

    if (!$timestamp || !$signature || !ctype_digit($timestamp)) {
        return new WP_Error('content_os_auth_missing', 'Missing signed Content Desk authentication.', array('status' => 401));
    }
    if (abs(time() - intval($timestamp)) > 300) {
        return new WP_Error('content_os_auth_expired', 'Content Desk signature expired.', array('status' => 401));
    }

    $body_hash = hash('sha256', (string) $request->get_body());
    $query_hash = hash('sha256', keys_content_os_query_string($request));
    $canonical = strtoupper($request->get_method()) . "\n" . $request->get_route() . "\n" . $timestamp . "\n" . $body_hash . "\n" . $query_hash;
    $expected = hash_hmac('sha256', $canonical, $secret);

    if (!hash_equals($expected, $signature)) {
        return new WP_Error('content_os_auth_invalid', 'Invalid Content Desk signature.', array('status' => 401));
    }
    return true;
}

add_action('rest_api_init', function () {
    register_rest_route('keys-content-os/v1', '/ping', array(
        'methods' => 'GET',
        'callback' => function () {
            return array('ok' => true, 'version' => KEYS_CONTENT_OS_VERSION, 'site' => home_url('/'));
        },
        'permission_callback' => 'keys_content_os_permission',
    ));

    register_rest_route('keys-content-os/v1', '/products', array(
        'methods' => 'GET',
        'callback' => 'keys_content_os_products',
        'permission_callback' => 'keys_content_os_permission',
    ));

    register_rest_route('keys-content-os/v1', '/categories', array(
        'methods' => 'GET',
        'callback' => 'keys_content_os_categories',
        'permission_callback' => 'keys_content_os_permission',
    ));

    register_rest_route('keys-content-os/v1', '/media', array(
        'methods' => 'POST',
        'callback' => 'keys_content_os_media',
        'permission_callback' => 'keys_content_os_permission',
    ));

    register_rest_route('keys-content-os/v1', '/posts', array(
        'methods' => 'POST',
        'callback' => 'keys_content_os_create_post',
        'permission_callback' => 'keys_content_os_permission',
    ));
});

function keys_content_os_product_row($product) {
    if (!$product || !is_a($product, 'WC_Product')) { return null; }
    $terms = wp_get_post_terms($product->get_id(), 'product_cat', array('fields' => 'names'));
    return array(
        'id' => $product->get_id(),
        'kind' => 'product',
        'title' => $product->get_name(),
        'slug' => get_post_field('post_name', $product->get_id()),
        'url' => get_permalink($product->get_id()),
        'sku' => $product->get_sku(),
        'category' => is_wp_error($terms) ? '' : implode(', ', $terms),
        'status' => get_post_status($product->get_id()),
    );
}

function keys_content_os_products(WP_REST_Request $request) {
    if (!function_exists('wc_get_product')) {
        return new WP_Error('woocommerce_missing', 'WooCommerce is not active.', array('status' => 500));
    }
    $q = sanitize_text_field((string) $request->get_param('q'));
    $limit = max(1, min(30, intval($request->get_param('limit') ?: 15)));
    if (strlen($q) < 2) { return array(); }

    $ids = array();
    $title_query = new WP_Query(array(
        'post_type' => 'product', 'post_status' => 'publish', 's' => $q,
        'posts_per_page' => $limit, 'fields' => 'ids', 'no_found_rows' => true,
    ));
    foreach ($title_query->posts as $id) { $ids[intval($id)] = true; }

    $sku_query = new WP_Query(array(
        'post_type' => 'product', 'post_status' => 'publish', 'posts_per_page' => $limit,
        'fields' => 'ids', 'no_found_rows' => true,
        'meta_query' => array(array('key' => '_sku', 'value' => $q, 'compare' => 'LIKE')),
    ));
    foreach ($sku_query->posts as $id) { $ids[intval($id)] = true; }

    $rows = array();
    foreach (array_slice(array_keys($ids), 0, $limit) as $id) {
        $row = keys_content_os_product_row(wc_get_product($id));
        if ($row) { $rows[] = $row; }
    }
    return $rows;
}

function keys_content_os_categories(WP_REST_Request $request) {
    $q = sanitize_text_field((string) $request->get_param('q'));
    $limit = max(1, min(30, intval($request->get_param('limit') ?: 15)));
    $terms = get_terms(array(
        'taxonomy' => 'product_cat', 'hide_empty' => false, 'number' => $limit,
        'search' => $q,
    ));
    if (is_wp_error($terms)) { return $terms; }
    $rows = array();
    foreach ($terms as $term) {
        $rows[] = array(
            'id' => $term->term_id,
            'kind' => 'category',
            'title' => $term->name,
            'slug' => $term->slug,
            'url' => get_term_link($term),
            'sku' => '',
            'category' => '',
            'status' => 'publish',
        );
    }
    return $rows;
}

function keys_content_os_media(WP_REST_Request $request) {
    $filename = sanitize_file_name((string) $request->get_header('x-content-desk-filename'));
    $alt = sanitize_text_field((string) $request->get_header('x-content-desk-alt'));
    $bytes = $request->get_body();
    if (!$filename || !$bytes) {
        return new WP_Error('media_missing', 'Filename and image data are required.', array('status' => 400));
    }
    if (strlen($bytes) > 6 * 1024 * 1024) {
        return new WP_Error('media_too_large', 'Image exceeds 6 MB.', array('status' => 413));
    }
    $upload = wp_upload_bits($filename, null, $bytes);
    if (!empty($upload['error'])) {
        return new WP_Error('media_upload_failed', $upload['error'], array('status' => 500));
    }
    $filetype = wp_check_filetype($filename, null);
    $attachment_id = wp_insert_attachment(array(
        'post_mime_type' => $filetype['type'],
        'post_title' => sanitize_text_field(pathinfo($filename, PATHINFO_FILENAME)),
        'post_status' => 'inherit',
    ), $upload['file']);
    if (is_wp_error($attachment_id)) { return $attachment_id; }
    require_once ABSPATH . 'wp-admin/includes/image.php';
    $metadata = wp_generate_attachment_metadata($attachment_id, $upload['file']);
    wp_update_attachment_metadata($attachment_id, $metadata);
    if ($alt) { update_post_meta($attachment_id, '_wp_attachment_image_alt', $alt); }
    return array('id' => $attachment_id, 'url' => wp_get_attachment_url($attachment_id));
}

function keys_content_os_create_post(WP_REST_Request $request) {
    $data = $request->get_json_params();
    if (!is_array($data)) { $data = array(); }
    $title = sanitize_text_field((string) ($data['title'] ?? ''));
    $slug = sanitize_title((string) ($data['slug'] ?? $title));
    if (!$title || !$slug) {
        return new WP_Error('post_missing', 'Title and slug are required.', array('status' => 400));
    }
    $existing = get_page_by_path($slug, OBJECT, 'post');
    if ($existing) {
        return new WP_Error('duplicate_slug', 'A WordPress post with this slug already exists.', array('status' => 409));
    }
    $allowed_status = array('draft', 'pending', 'future', 'publish');
    $status = in_array(($data['status'] ?? 'draft'), $allowed_status, true) ? $data['status'] : 'draft';
    $author = get_user_by('login', 'contentdesk');

    $postarr = array(
        'post_type' => 'post',
        'post_title' => $title,
        'post_name' => $slug,
        'post_content' => wp_kses_post((string) ($data['content'] ?? '')),
        'post_excerpt' => sanitize_textarea_field((string) ($data['excerpt'] ?? '')),
        'post_status' => $status,
    );
    if ($author) { $postarr['post_author'] = $author->ID; }
    if (!empty($data['date'])) { $postarr['post_date'] = sanitize_text_field($data['date']); }

    $post_id = wp_insert_post($postarr, true);
    if (is_wp_error($post_id)) { return $post_id; }

    if (!empty($data['categories']) && is_array($data['categories'])) {
        wp_set_post_categories($post_id, array_map('intval', $data['categories']), false);
    }
    if (!empty($data['tags']) && is_array($data['tags'])) {
        wp_set_post_terms($post_id, array_map('intval', $data['tags']), 'post_tag', false);
    }
    if (!empty($data['featured_media'])) { set_post_thumbnail($post_id, intval($data['featured_media'])); }
    if (!empty($data['meta_title'])) { update_post_meta($post_id, '_yoast_wpseo_title', sanitize_text_field($data['meta_title'])); }
    if (!empty($data['meta_description'])) { update_post_meta($post_id, '_yoast_wpseo_metadesc', sanitize_text_field($data['meta_description'])); }

    return array(
        'id' => $post_id,
        'url' => get_permalink($post_id),
        'status' => get_post_status($post_id),
    );
}

add_action('admin_menu', function () {
    add_options_page('Keys Content OS', 'Keys Content OS', 'manage_options', 'keys-content-os', 'keys_content_os_settings_page');
});

function keys_content_os_settings_page() {
    if (!current_user_can('manage_options')) { return; }
    if (isset($_POST['keys_content_os_regenerate']) && check_admin_referer('keys_content_os_regenerate')) {
        try { $secret = bin2hex(random_bytes(32)); }
        catch (Exception $e) { $secret = wp_generate_password(64, true, true); }
        update_option(KEYS_CONTENT_OS_SECRET_OPTION, $secret, false);
        echo '<div class="notice notice-success"><p>Bridge secret regenerated. Update .env.keys-shop before the next Content Desk request.</p></div>';
    }
    $secret = esc_attr(keys_content_os_secret());
    echo '<div class="wrap"><h1>Keys Content OS Bridge</h1>';
    echo '<p>Copy this secret into <code>.env.keys-shop</code> as <code>KEYS_CONTENT_OS_SECRET=...</code>.</p>';
    echo '<input type="text" readonly style="width:620px;max-width:100%;font-family:monospace" value="' . $secret . '">';
    echo '<form method="post" style="margin-top:18px">';
    wp_nonce_field('keys_content_os_regenerate');
    echo '<button class="button" name="keys_content_os_regenerate" value="1">Regenerate Secret</button>';
    echo '</form></div>';
}
