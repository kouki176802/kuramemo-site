<?php get_header(); ?>
<section class="hero">
  <div class="hero-copy">
    <div class="eyebrow">SNS・ニュースの注目商品</div>
    <h1><span>SNSとニュースの</span><span>話題を先取り</span></h1>
    <p class="hero-lead">いま注目されている商品やサービスを見つけて<br>用途・条件・価格から選びやすく整理します<br><strong>話題だけで決めず 納得できる一品へ</strong></p>
    <div class="hero-actions"><a class="button button-primary" href="#latest">最新の商品ガイドを見る</a></div>
  </div>
  <div class="hero-showcase">
    <div class="hero-feature-card">
      <span>BOT SCREENING</span><strong>話題と売れ筋を照合</strong>
      <p>ニュースの注目理由と、販売中の商品情報を分けて確認します</p>
    </div>
    <div class="hero-notes">
      <a href="#latest"><b>01</b><span>どこで話題か</span></a>
      <a href="#latest"><b>02</b><span>なぜ注目か</span></a>
      <a href="#latest"><b>03</b><span>誰に向くか</span></a>
    </div>
  </div>
</section>

<section class="comparison-index" id="latest">
  <div class="section-kicker">最新の商品ガイド</div>
  <h2>気になるものから開く</h2>
  <div class="article-grid">
    <?php
    $latest = new WP_Query(['post_type' => 'post', 'post_status' => 'publish', 'posts_per_page' => 9]);
    if ($latest->have_posts()) : while ($latest->have_posts()) : $latest->the_post(); ?>
      <a class="article-card" href="<?php the_permalink(); ?>">
        <figure><?php if (has_post_thumbnail()) { the_post_thumbnail('medium'); } else { ?><span class="figure-mark">NEW</span><?php } ?></figure>
        <span><?php echo esc_html(get_the_category()[0]->name ?? 'Guide'); ?></span>
        <h3><?php the_title(); ?></h3>
        <p><?php echo esc_html(wp_trim_words(get_the_excerpt(), 42)); ?></p>
      </a>
    <?php endwhile; wp_reset_postdata(); else : ?>
      <article class="article-card"><span>準備中</span><h3>最初の記事を待っています</h3><p>BOTから下書きを送ると、ここに商品ガイドが並びます。</p></article>
    <?php endif; ?>
  </div>
</section>
<?php get_footer(); ?>
