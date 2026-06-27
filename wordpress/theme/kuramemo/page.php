<?php get_header(); ?>
<section class="page-card wp-article">
<?php while (have_posts()) : the_post(); ?>
  <h1><?php the_title(); ?></h1>
  <article class="wp-entry-content"><?php the_content(); ?></article>
<?php endwhile; ?>
</section>
<?php get_footer(); ?>
