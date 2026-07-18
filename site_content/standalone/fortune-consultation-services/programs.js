/*
 * 参加中の占いプログラム一覧
 *
 * 追加方法:
 * 1. A8.netで参加中・掲載媒体・広告素材の有効性を確認
 * 2. 下の配列へ1件追加
 * 3. statusを "active" にすると、typeに対応する一覧へ自動表示
 *
 * type: phone / chat / mail / comprehensive
 * status: active のみ公開。pending / paused は公開されません。
 */
window.FORTUNE_PROGRAMS = [
  {
    id: "coconala",
    name: "ココナラ電話占い",
    brand: "COCONALA",
    type: "phone",
    status: "active",
    featured: true,
    asp: "A8.net",
    verifiedAt: "2026-07-05",
    label: "相談相手の情報を見て選びたい人に",
    featureTitle: "出品者情報と相談テーマから、自分に合いそうな相手を探せる",
    featurePoints: ["候補を比較しやすい", "対面せず電話相談", "予算から検討しやすい"],
    description: "出品者情報や相談テーマを見比べて、対面せず電話で相談したい人向けです。",
    fit: "相談テーマと予算を決め、候補を比較して選びたい人",
    avoid: "時間や支出を自分で止めにくい人／専門判断が必要な人",
    checks: "占い師ごとの1分料金・通話料・特典上限・キャンセル条件",
    affiliateUrl: "https://px.a8.net/svt/ejp?a8mat=4B7ROY+2BY52Q+2PEO+C5VW1",
    trackingPixel: "https://www17.a8.net/0.gif?a8mat=4B7ROY+2BY52Q+2PEO+C5VW1",
    cta: "ココナラの公式条件を見る",
    visual: "visual-chat"
  },
  {
    id: "vernis",
    name: "電話占いヴェルニ",
    brand: "VERNIS",
    type: "phone",
    status: "active",
    featured: false,
    asp: "A8.net",
    verifiedAt: "2026-07-05",
    label: "在籍占い師の選択肢を広く見たい人に",
    featureTitle: "幅広い候補から、相談内容や条件に合う占い師を絞り込める",
    featurePoints: ["在籍候補を広く比較", "相談内容から検討", "予約条件も確認できる"],
    description: "在籍占い師の選択肢を広く見ながら、相談内容や条件に合う候補を探したい人向けです。",
    fit: "複数の占い師を比較してから電話相談したい人",
    avoid: "文章だけで相談したい人／予算上限を決めにくい人",
    checks: "1分料金・通話料・初回特典・予約・支払方法",
    affiliateUrl: "https://px.a8.net/svt/ejp?a8mat=4B7ROY+EAFAQ+2H0Q+TUVZL",
    trackingPixel: "https://www18.a8.net/0.gif?a8mat=4B7ROY+EAFAQ+2H0Q+TUVZL",
    cta: "ヴェルニの公式条件を見る",
    visual: "visual-phone"
  }
];
