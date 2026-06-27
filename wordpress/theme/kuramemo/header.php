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
    <?php foreach (kuramemo_categories() as $label) :
      $category = get_category_by_slug(sanitize_title($label));
      $url = $category ? get_category_link($category) : home_url('/?s=' . rawurlencode($label));
    ?>
      <a href="<?php echo esc_url($url); ?>"><span><?php echo esc_html($label); ?></span></a>
    <?php endforeach; ?>
  </nav>
</header>
<main>
