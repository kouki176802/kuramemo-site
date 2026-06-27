<?php get_header(); ?>
<section class="page-card wp-article">
<?php while (have_posts()) : the_post(); ?>
  <div class="section-kicker">商品ガイド</div>
  <h1><?php the_title(); ?></h1>
  <p class="wp-article-meta">更新 <?php echo esc_html(get_the_modified_date('Y.m.d')); ?>　広告リンクを含む場合があります</p>
  <article class="wp-entry-content"><?php the_content(); ?></article>
<?php endwhile; ?>
</section>
<?php get_footer(); ?>
