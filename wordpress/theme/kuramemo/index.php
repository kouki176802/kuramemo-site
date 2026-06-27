<?php get_header(); ?>
<section class="comparison-index">
  <div class="section-kicker">商品ガイド</div>
  <h1><?php single_post_title(); ?></h1>
  <div class="article-grid">
  <?php if (have_posts()) : while (have_posts()) : the_post(); ?>
    <a class="article-card" href="<?php the_permalink(); ?>">
      <figure><?php if (has_post_thumbnail()) { the_post_thumbnail('medium'); } else { ?><span class="figure-mark">NEW</span><?php } ?></figure>
      <span><?php echo esc_html(get_the_category()[0]->name ?? 'Guide'); ?></span>
      <h3><?php the_title(); ?></h3><p><?php echo esc_html(wp_trim_words(get_the_excerpt(), 42)); ?></p>
    </a>
  <?php endwhile; else : ?><p>記事はまだありません。</p><?php endif; ?>
  </div>
</section>
<?php get_footer(); ?>
