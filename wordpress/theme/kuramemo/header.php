<!doctype html>
<html <?php language_attributes(); ?>>
<head>
  <meta charset="<?php bloginfo('charset'); ?>">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>
<header class="site-header">
  <a class="brand" href="<?php echo esc_url(home_url('/')); ?>">
    <span>くらメモ</span><small>買う前チェック</small>
  </a>
  <nav aria-label="主要カテゴリ">
    <a href="<?php echo esc_url(home_url('/')); ?>" <?php if (is_front_page()) echo 'aria-current="page"'; ?>><span>トップ</span></a>
    <?php foreach (kuramemo_nav_items() as $label => $slug) : ?>
      <a href="<?php echo esc_url(home_url('/' . $slug . '/')); ?>" <?php if (is_page($slug)) echo 'aria-current="page"'; ?>><span><?php echo esc_html($label); ?></span></a>
    <?php endforeach; ?>
    <a href="<?php echo esc_url(home_url('/advertising-policy/')); ?>" <?php if (is_page('advertising-policy')) echo 'aria-current="page"'; ?>><span>広告方針</span></a>
  </nav>
</header>
<main>
