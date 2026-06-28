<?php get_header();
$generated = kuramemo_generated_main_html();
if ($generated) {
    echo $generated; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- trusted local artifact
} else {
?>
  <section class="page-card wp-article">
  <?php while (have_posts()) : the_post(); ?>
    <div class="section-kicker">くらメモ</div>
    <h1><?php the_title(); ?></h1>
    <article class="wp-entry-content"><?php the_content(); ?></article>
  <?php endwhile; ?>
  </section>
<?php }
get_footer(); ?>
