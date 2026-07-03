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
    $generated_css = get_template_directory() . '/generated/styles.css';
    $generated_js = get_template_directory() . '/generated/click-tracker.js';
    $generated_version = is_readable($generated_css) ? (string) filemtime($generated_css) : $theme->get('Version');
    $tracker_version = is_readable($generated_js) ? (string) filemtime($generated_js) : $theme->get('Version');
    wp_enqueue_style('kuramemo-generated', get_template_directory_uri() . '/generated/styles.css', [], $generated_version);
    wp_enqueue_style('kuramemo-wordpress', get_template_directory_uri() . '/wordpress.css', ['kuramemo-generated'], $theme->get('Version'));
    wp_enqueue_script('kuramemo-click-tracker', get_template_directory_uri() . '/generated/click-tracker.js', [], $tracker_version, true);
});

add_filter('body_class', static function ($classes) {
    $classes[] = is_front_page() ? 'home' : 'subpage';
    return $classes;
});

function kuramemo_categories() {
    return [
        'AI・ガジェット', '美容', 'フィットネス', '健康', '季節・暮らし',
        '防災・備蓄', '家事・時短', '旅行・外出', '通信・学び・お金',
    ];
}

function kuramemo_nav_items() {
    return [
        'AI・ガジェット' => 'category-ai-gadgets',
        '美容' => 'category-beauty',
        'フィットネス' => 'category-fitness',
        '健康' => 'category-health',
        '季節・暮らし' => 'category-lifestyle-seasonal',
        '防災・備蓄' => 'category-disaster-preparedness',
        '家事・時短' => 'category-housework-timesaving',
        '旅行・外出' => 'category-travel-outdoor',
        '通信・学び・お金' => 'category-services',
    ];
}

function kuramemo_generated_slug() {
    if (is_front_page()) {
        return 'index';
    }
    if (is_page()) {
        return get_post_field('post_name', get_queried_object_id());
    }
    return '';
}

function kuramemo_generated_main_html($slug = '') {
    $slug = $slug ?: kuramemo_generated_slug();
    if (!$slug || !preg_match('/^[a-z0-9-]+$/', $slug)) {
        return '';
    }
    $filename = $slug === 'index' ? 'index.html' : $slug . '.html';
    $path = get_template_directory() . '/generated/' . $filename;
    if (!is_readable($path)) {
        return '';
    }
    $document = file_get_contents($path);
    if (!preg_match('/<main[^>]*>(.*?)<\/main>/si', $document, $match)) {
        return '';
    }
    $content = $match[1];
    $asset_base = trailingslashit(get_template_directory_uri() . '/generated');
    $content = preg_replace_callback(
        '/\b(src|href)=(\"|\')assets\/([^\"\']+)\2/i',
        static function ($parts) use ($asset_base) {
            return $parts[1] . '=' . $parts[2] . esc_url($asset_base . 'assets/' . $parts[3]) . $parts[2];
        },
        $content
    );
    $content = preg_replace_callback(
        '/href=(\"|\')(?!https?:\/\/|\/\/|#|mailto:)([^\"\']+?)\.html(#[^\"\']*)?\1/i',
        static function ($parts) {
            $page_slug = $parts[2] === 'index' ? '' : trim($parts[2], '/');
            $url = $page_slug ? home_url('/' . $page_slug . '/') : home_url('/');
            return 'href=' . $parts[1] . esc_url($url . ($parts[3] ?? '')) . $parts[1];
        },
        $content
    );
    return $content;
}

add_filter('document_title_parts', static function ($parts) {
    $slug = kuramemo_generated_slug();
    if (!$slug) {
        return $parts;
    }
    $filename = $slug === 'index' ? 'index.html' : $slug . '.html';
    $path = get_template_directory() . '/generated/' . $filename;
    if (is_readable($path) && preg_match('/<title>(.*?)<\/title>/si', file_get_contents($path), $match)) {
        $parts['title'] = wp_strip_all_tags(str_replace(' | くらメモ', '', $match[1]));
    }
    return $parts;
});

add_action('wp_head', static function () {
    $slug = kuramemo_generated_slug();
    if (!$slug) {
        return;
    }
    $filename = $slug === 'index' ? 'index.html' : $slug . '.html';
    $path = get_template_directory() . '/generated/' . $filename;
    if (!is_readable($path)) {
        return;
    }
    $document = file_get_contents($path);
    if (preg_match('/<meta name="description" content="([^"]*)">/i', $document, $description)) {
        echo '<meta name="description" content="' . esc_attr(html_entity_decode($description[1], ENT_QUOTES, 'UTF-8')) . '">' . "\n";
    }
}, 2);
