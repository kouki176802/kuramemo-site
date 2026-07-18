const PROGRAM_TYPES = [
  { id: 'phone', label: '電話占い', icon: '◡', lead: '声で話しながら、今の気持ちや選択肢を整理したい人へ。', empty: '参加中の電話占いプログラムはまだありません。' },
  { id: 'chat', label: 'チャット占い', icon: '···', lead: '短い文章でやりとりし、相談内容を記録に残したい人へ。', empty: '参加中のチャット占いプログラムが増えると、ここに表示されます。' },
  { id: 'mail', label: 'メール占い', icon: '✉', lead: '経緯や質問をじっくり書いてから相談したい人へ。', empty: '参加中のメール占いプログラムが増えると、ここに表示されます。' },
  { id: 'comprehensive', label: '総合占い', icon: '✦', lead: '複数の相談方法や占術から、自分の条件で選びたい人へ。', empty: '参加中の総合占いプログラムが増えると、ここに表示されます。' }
];

const SOCIAL_SOURCE_LABELS = {
  instagram: 'Instagramの投稿からお越しの方へ',
  youtube: 'YouTubeの動画からお越しの方へ',
  tiktok: 'TikTokの動画からお越しの方へ',
  x: 'Xの投稿からお越しの方へ',
  twitter: 'Xの投稿からお越しの方へ',
  line: 'LINEのシェアからお越しの方へ'
};

const currentParams = new URLSearchParams(window.location.search);
const socialSource = (currentParams.get('utm_source') || '').toLowerCase();
const socialCampaign = currentParams.get('utm_campaign') || '';
const socialContent = currentParams.get('utm_content') || '';

if (socialSource) {
  try {
    sessionStorage.setItem('kuramemo_social_attribution', JSON.stringify({
      source: socialSource,
      campaign: socialCampaign,
      content: socialContent,
      arrivedAt: new Date().toISOString()
    }));
  } catch (_) {
    // Storage is optional; the page works without it.
  }
}

const socialArrival = document.querySelector('#social-arrival');
const socialArrivalLabel = document.querySelector('#social-arrival-label');
if (socialArrival && socialArrivalLabel && SOCIAL_SOURCE_LABELS[socialSource]) {
  socialArrivalLabel.textContent = SOCIAL_SOURCE_LABELS[socialSource];
  socialArrival.hidden = false;
  document.body.dataset.socialSource = socialSource;
}

const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[character]));

const activePrograms = (window.FORTUNE_PROGRAMS || []).filter((program) => (
  program.status === 'active' && program.affiliateUrl
));

const renderProgramCard = (program) => `
  <article class="offer-card program-card ${program.featured ? 'featured' : ''} reveal" id="service-${escapeHtml(program.id)}">
    ${program.featured ? `<div class="recommend-ribbon">${escapeHtml(program.label)}</div>` : ''}
    <div class="offer-top">
      <span class="offer-label">${escapeHtml(PROGRAM_TYPES.find((type) => type.id === program.type)?.label || '占いサービス')}</span>
      <span class="offer-ad">PR・${escapeHtml(program.asp)}</span>
    </div>
    <div class="offer-visual ${escapeHtml(program.visual || 'visual-phone')}">
      <span>${escapeHtml(program.brand)}</span>
      <b>${escapeHtml(program.name)}</b>
    </div>
    <p class="program-verified">参加中確認 ${escapeHtml((program.verifiedAt || '確認日未設定').replace(/-/g, '.'))}</p>
    <h4>${escapeHtml(program.name)}</h4>
    <div class="feature-spotlight">
      <small>このサービスの特徴</small>
      <strong>${escapeHtml(program.featureTitle)}</strong>
    </div>
    <ul class="feature-points">
      ${(program.featurePoints || []).map((point) => `<li>${escapeHtml(point)}</li>`).join('')}
    </ul>
    <p class="program-description">${escapeHtml(program.description)}</p>
    <dl>
      <div><dt>向いている人</dt><dd>${escapeHtml(program.fit)}</dd></div>
      <div><dt>向かない人</dt><dd>${escapeHtml(program.avoid)}</dd></div>
    </dl>
    <div class="offer-check"><b>申し込み前に</b><span>${escapeHtml(program.checks)}</span></div>
    <a class="button ${program.featured ? 'button-primary' : 'button-outline'} affiliate-link" href="${escapeHtml(program.affiliateUrl)}" rel="nofollow sponsored noopener" target="_blank" data-offer="${escapeHtml(program.id)}">${escapeHtml(program.cta)} <span>→</span></a>
    ${program.trackingPixel ? `<img class="affiliate-tracker" width="1" height="1" src="${escapeHtml(program.trackingPixel)}" alt="">` : ''}
  </article>`;

const programNav = document.querySelector('#program-type-nav');
const programGroups = document.querySelector('#program-groups');

if (programNav && programGroups) {
  programNav.innerHTML = PROGRAM_TYPES.map((type) => {
    const count = activePrograms.filter((program) => program.type === type.id).length;
    return `<a href="#program-${type.id}"><span>${type.icon}</span>${type.label}<small>${count}</small></a>`;
  }).join('');

  programGroups.innerHTML = PROGRAM_TYPES.map((type) => {
    const programs = activePrograms.filter((program) => program.type === type.id);
    return `
      <section class="program-group" id="program-${type.id}" aria-labelledby="program-${type.id}-title">
        <div class="program-group-heading">
          <span class="method-icon ${type.id}">${type.icon}</span>
          <div><p>TYPE / ${type.id.toUpperCase()}</p><h3 id="program-${type.id}-title">${type.label}</h3><small>${type.lead}</small></div>
          <b>${programs.length}件掲載</b>
        </div>
        ${programs.length
          ? `<div class="offer-grid actual-offers">${programs.map(renderProgramCard).join('')}</div>`
          : `<div class="program-empty"><span>${type.icon}</span><div><b>現在、掲載準備中です</b><p>${type.empty}</p></div></div>`}
      </section>`;
  }).join('');
}

const revealItems = document.querySelectorAll('.reveal');

if ('IntersectionObserver' in window) {
  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  revealItems.forEach((item) => revealObserver.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add('visible'));
}

const tabs = document.querySelectorAll('.story-tab');
const stories = document.querySelectorAll('.story-card');

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    const filter = tab.dataset.filter;
    tabs.forEach((item) => {
      item.classList.toggle('active', item === tab);
      item.setAttribute('aria-selected', String(item === tab));
    });
    stories.forEach((story) => {
      story.classList.toggle('is-hidden', filter !== 'all' && story.dataset.category !== filter);
    });
  });
});

const resultButton = document.querySelector('#show-result');
const resultBox = document.querySelector('#diagnosis-result');

const resultCopy = {
  phone: '<b>電話鑑定タイプが合いそうです</b>声で話しながら整理したい方向け。分単価・通話料・終了時間を決めてから候補を比べましょう。<br><a href="#program-phone">掲載中の電話占いを見る →</a>',
  chat: '<b>チャット鑑定タイプが合いそうです</b>短いやりとりを記録に残したい方向け。課金単位と履歴の保存期間を確認しましょう。<br><a href="#program-chat">チャット占い一覧を見る →</a>',
  mail: '<b>メール鑑定タイプが合いそうです</b>背景や質問をじっくり整理したい方向け。回答納期と追加質問の条件を確認しましょう。<br><a href="#program-mail">メール占い一覧を見る →</a>'
};

resultButton?.addEventListener('click', () => {
  const answers = [...document.querySelectorAll('.diagnosis-card input:checked')].map((input) => input.value);
  if (answers.length < 3) {
    resultBox.innerHTML = '<b>あと少しです</b>3つの質問すべてに答えると、合いそうな相談方法を表示します。';
  } else {
    const scores = {
      phone: answers.filter((answer) => answer === 'phone').length,
      chat: answers.filter((answer) => answer === 'text' || answer === 'quick').length,
      mail: answers.filter((answer) => answer === 'mail').length + (answers.includes('text') ? 0.5 : 0)
    };
    const winner = Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0];
    resultBox.innerHTML = resultCopy[winner];
  }
  resultBox.classList.add('show');
});

document.querySelectorAll('.faq-list details').forEach((detail) => {
  detail.addEventListener('toggle', () => {
    if (!detail.open) return;
    document.querySelectorAll('.faq-list details[open]').forEach((openDetail) => {
      if (openDetail !== detail) openDetail.removeAttribute('open');
    });
  });
});

const sticky = document.querySelector('#mobile-sticky');
const finalCta = document.querySelector('#final-cta');
if (sticky && finalCta && 'IntersectionObserver' in window) {
  const stickyObserver = new IntersectionObserver(([entry]) => {
    sticky.classList.toggle('is-hidden', entry.isIntersecting);
  }, { threshold: 0.1 });
  stickyObserver.observe(finalCta);
}

document.querySelectorAll('.affiliate-link').forEach((link) => {
  link.addEventListener('click', () => {
    console.info(`Affiliate link clicked: ${link.dataset.offer}`);
    if (typeof window.gtag === 'function') {
      window.gtag('event', 'affiliate_click', {
        program: link.dataset.offer,
        social_source: socialSource || 'direct',
        social_campaign: socialCampaign || 'none'
      });
    }
  });
});

const canonicalUrl = document.querySelector('link[rel="canonical"]')?.href || window.location.href;
const cleanShareUrl = new URL(canonicalUrl);
['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach((key) => cleanShareUrl.searchParams.delete(key));
cleanShareUrl.hash = '';
const shareTitle = '答えがほしい夜に。占い体験談と相談方法を比べるガイド';
const xShare = document.querySelector('#share-x');
const lineShare = document.querySelector('#share-line');
const copyShare = document.querySelector('#share-copy');
const shareStatus = document.querySelector('#share-status');

if (xShare) {
  xShare.href = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareTitle)}&url=${encodeURIComponent(cleanShareUrl.href)}`;
}
if (lineShare) {
  lineShare.href = `https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(cleanShareUrl.href)}`;
}
copyShare?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(cleanShareUrl.href);
    shareStatus.textContent = 'URLをコピーしました。';
  } catch (_) {
    shareStatus.textContent = 'コピーできませんでした。ブラウザーのアドレス欄からコピーしてください。';
  }
});

document.querySelectorAll('[data-route]').forEach((route) => {
  route.addEventListener('click', () => {
    if (typeof window.gtag === 'function') {
      window.gtag('event', 'sns_route_click', {
        route: route.dataset.route,
        social_source: socialSource || 'direct'
      });
    }
  });
});
