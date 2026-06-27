<?php
/**
 * Plugin Name: くらメモ ローカル安全設定
 * Description: 自宅PCでの検証中に検索エンジン公開と不用意な外部公開を防ぎます。
 */

if (!defined('ABSPATH')) {
    exit;
}

add_filter('pre_option_blog_public', static function () {
    return '0';
});

add_action('send_headers', static function () {
    header('X-Robots-Tag: noindex, nofollow, noarchive', true);
    header('X-Content-Type-Options: nosniff', true);
    header('Referrer-Policy: strict-origin-when-cross-origin', true);
});

add_filter('xmlrpc_enabled', '__return_false');
