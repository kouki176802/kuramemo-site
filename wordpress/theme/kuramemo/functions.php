<?php
if (!defined('ABSPATH')) {
    exit;
}

add_action('after_setup_theme', static function () {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support('html5', ['search-form', 'gallery', 'caption', 'style', 'script']);
    register_nav_menus(['primary' => '主要メニュー']);
});

add_action('wp_enqueue_scripts', static function () {
    $theme = wp_get_theme();
    wp_enqueue_style('kuramemo-generated', get_template_directory_uri() . '/generated/styles.css', [], $theme->get('Version'));
    wp_enqueue_style('kuramemo-wordpress', get_template_directory_uri() . '/wordpress.css', ['kuramemo-generated'], $theme->get('Version'));
});

add_filter('body_class', static function ($classes) {
    $classes[] = is_front_page() ? 'home' : 'subpage';
    return $classes;
});

function kuramemo_categories() {
    return [
        'AI・ガジェット', '美容', 'フィットネス', '健康', '季節・暮らし',
        '防災・備蓄', '家事・時短', '旅行・外出',
    ];
}
