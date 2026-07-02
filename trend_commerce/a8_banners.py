from __future__ import annotations

import html


# A8.netで2026-07-03に「参加中」と確認できた広告素材だけを収録する。
# 1x1画像も成果計測に必要なため、A8が発行したコードを改変せず保持する。
A8_BANNERS = {
    "hair-care": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+C9681E+4P4W+609HT" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="白髪染めカラートリートメント" src="https://www24.a8.net/svt/bgt?aid=260702962741&wid=001&eno=01&mid=s00000021920001009000&mc=1"></a><img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=4B7ROY+C9681E+4P4W+609HT" alt="">',
    "fitness-food": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+C6SHMA+4CPY+62MDD" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="Muscle Deli" src="https://www24.a8.net/svt/bgt?aid=260702962737&wid=001&eno=01&mid=s00000020311001020000&mc=1"></a><img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4B7ROY+C6SHMA+4CPY+62MDD" alt="">',
    "body-care": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+BZNACY+59Z6+5Z6WX" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="整体ショーツNEO+" src="https://www28.a8.net/svt/bgt?aid=260702962725&wid=001&eno=01&mid=s00000024621001004000&mc=1"></a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B7ROY+BZNACY+59Z6+5Z6WX" alt="">',
    "internet": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+BPIX2Q+1MWA+1TQ96P" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="光回線申込み窓口" src="https://www26.a8.net/svt/bgt?aid=260702962708&wid=001&eno=01&mid=s00000007633011040000&mc=1"></a><img border="0" width="1" height="1" src="https://www14.a8.net/0.gif?a8mat=4B7ROY+BPIX2Q+1MWA+1TQ96P" alt="">',
    "preparedness": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+2J3CC2+5VK4+5YZ75" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="防災ブランド スツーレ" src="https://www20.a8.net/svt/bgt?aid=260702962153&wid=001&eno=01&mid=s00000027418001003000&mc=1"></a><img border="0" width="1" height="1" src="https://www14.a8.net/0.gif?a8mat=4B7ROY+2J3CC2+5VK4+5YZ75" alt="">',
    "preparedness-kit": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+2HWH4I+5HQC+5YZ75" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="あかまる防災44点セット" src="https://www21.a8.net/svt/bgt?aid=260702962151&wid=001&eno=01&mid=s00000025626001003000&mc=1"></a><img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=4B7ROY+2HWH4I+5HQC+5YZ75" alt="">',
    "meal": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+2GPLWY+4WD6+61RI9" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="DELIPICKS冷凍弁当" src="https://www21.a8.net/svt/bgt?aid=260702962149&wid=001&eno=01&mid=s00000022857001016000&mc=1"></a><img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4B7ROY+2GPLWY+4WD6+61RI9" alt="">',
    "fortune": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+2BY52Q+2PEO+C5VW1" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="ココナラ電話占い" src="https://www23.a8.net/svt/bgt?aid=260702962141&wid=001&eno=01&mid=s00000012624002043000&mc=1"></a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B7ROY+2BY52Q+2PEO+C5VW1" alt="">',
    "mini-pc": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+2BCPGY+5W12+5ZU29" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="GMKtecミニPC" src="https://www23.a8.net/svt/bgt?aid=260702962140&wid=001&eno=01&mid=s00000027479001007000&mc=1"></a><img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=4B7ROY+2BCPGY+5W12+5ZU29" alt="">',
    "beauty-serum": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+PLNSI+4TX4+1BNQZ5" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="Re:needleセラム" src="https://www29.a8.net/svt/bgt?aid=260702962043&wid=001&eno=01&mid=s00000022540008005000&mc=1"></a><img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4B7ROY+PLNSI+4TX4+1BNQZ5" alt="">',
    "shoes": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+P086Q+5W4O+5ZEMP" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="Kizikハンズフリーシューズ" src="https://www27.a8.net/svt/bgt?aid=260702962042&wid=001&eno=01&mid=s00000027492001005000&mc=1"></a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B7ROY+P086Q+5W4O+5ZEMP" alt="">',
    "health-test": '<a href="https://px.a8.net/svt/ejp?a8mat=4B7ROY+LGDU+5W26+5YZ75" rel="nofollow sponsored"><img border="0" width="300" height="250" alt="尿がん検査くん" src="https://www26.a8.net/svt/bgt?aid=260702962001&wid=001&eno=01&mid=s00000027483001003000&mc=1"></a><img border="0" width="1" height="1" src="https://www14.a8.net/0.gif?a8mat=4B7ROY+LGDU+5W26+5YZ75" alt="">',
}

A8_BANNER_DETAILS = {
    "hair-care": {"title": "白髪ケア用カラートリートメント", "description": "自宅で白髪をケアしたい人向けの商品広告です。色味だけでなく、使用頻度と継続費用も確認します。", "fit": "美容室の合間に自宅でケアしたい人", "check": "色展開、使用回数、定期購入条件、解約方法"},
    "internet": {
        "title": "光回線の申込み窓口",
        "description": "自宅のネット回線を新規契約・乗り換えしたい人向けの広告です。月額だけでなく、工事費や特典を含む実質負担で判断します。",
        "fit": "引っ越しや回線の見直しを予定している人",
        "check": "対応エリア、必須オプション、特典の受取条件・時期、契約期間",
    },
    "fortune": {
        "title": "ココナラ電話占い",
        "description": "電話で相談したい人向けのサービスです。初回特典には上限や対象条件があります。",
        "fit": "対面せず、都合のよい時間に相談したい人",
        "check": "1分あたりの料金、通話料、初回特典の上限、キャンセル条件",
    },
    "fitness-food": {"title": "Muscle Deli", "description": "栄養管理の手間を減らしたい人向けの宅配食です。目的別プランと1食あたりの費用を確認します。", "fit": "運動中の食事管理を続けやすくしたい人", "check": "内容量、栄養成分、配送頻度、定期購入条件"},
    "body-care": {"title": "整体ショーツNEO+", "description": "日常着として使う補整ショーツの商品広告です。サイズと着用感を確認し、医療効果を前提に選ばないようにします。", "fit": "普段の服装に取り入れやすい補整アイテムを探す人", "check": "サイズ表、素材、返品条件、定期購入の有無"},
    "preparedness": {"title": "防災ブランド スツーレ", "description": "非常時の備えをまとめて確認したい人向けの防災用品広告です。家族構成と避難方法に合わせて不足品を補います。", "fit": "防災用品を一から見直したい人", "check": "内容物、保存期限、人数、重量、保管場所"},
    "preparedness-kit": {"title": "あかまる防災44点セット", "description": "持ち出し用品をまとめて準備したい人向けです。点数よりも、自分に必要な水・食料・衛生用品の量を確認します。", "fit": "持ち出し袋の土台を短時間で作りたい人", "check": "中身の重複、保存期限、重量、追加が必要な個人用品"},
    "meal": {"title": "DELIPICKS冷凍弁当", "description": "献立や調理の時間を減らしたい人向けの冷凍宅配食です。送料を含む総額と保管スペースも見ます。", "fit": "忙しい日の食事を短時間で用意したい人", "check": "1食あたりの総額、送料、配送間隔、スキップ・解約条件"},
    "mini-pc": {"title": "GMKtecミニPC", "description": "省スペースのパソコンを探している人向けの広告です。用途に必要な性能と端子を先に確認します。", "fit": "机を広く使いながら日常作業をしたい人", "check": "CPU・メモリ・容量、端子、OS、保証と返品条件"},
    "beauty-serum": {"title": "Re:needleセラム", "description": "自宅のスキンケアに美容液を追加したい人向けです。使用感には個人差があります。", "fit": "成分と使用手順を確認してケアを続けたい人", "check": "全成分、使用頻度、肌に合わない場合の対応、定期購入条件"},
    "shoes": {"title": "Kizikハンズフリーシューズ", "description": "かがまずに履きやすい靴を探している人向けの商品広告です。歩き方に合うサイズと返品条件を確認します。", "fit": "外出時の靴の脱ぎ履きを楽にしたい人", "check": "サイズ感、幅、重量、交換・返品条件"},
    "health-test": {"title": "尿がん検査くん", "description": "自宅で検体を採取する検査サービスの広告です。診断の代わりではないため、対象範囲と受診が必要な場合を確認します。", "fit": "検査方法と限界を理解して健康確認のきっかけにしたい人", "check": "検査対象、精度の説明、結果通知、陽性・不安時の医療機関受診"},
}


def banner_keys_for_slug(slug: str) -> list[str]:
    if slug in {
        "about", "advertising-policy", "disclaimer", "editorial-policy", "privacy-policy",
        "privacy-policy-template", "404", "credit-card-services", "investment-account-services",
        "streaming-services", "ai-school-services", "hair-removal-services",
    }:
        return []
    if "disaster" in slug:
        return ["preparedness", "preparedness-kit"]
    if any(word in slug for word in ("ai", "pc", "gadget", "charging")):
        return ["mini-pc"]
    if any(word in slug for word in ("beauty", "skin", "hair", "groom")):
        return ["beauty-serum", "hair-care"]
    if "fitness" in slug or "training" in slug:
        return ["fitness-food", "body-care"]
    if "health" in slug:
        return ["health-test"]
    if slug == "category-services":
        return ["internet", "fortune"]
    if "internet" in slug or "carrier" in slug:
        return ["internet"]
    if "fortune" in slug:
        return ["fortune"]
    if any(word in slug for word in ("housework", "kitchen", "living")):
        return ["meal"]
    if any(word in slug for word in ("travel", "outdoor")):
        return ["shoes"]
    if slug == "index":
        return ["mini-pc", "beauty-serum", "preparedness"]
    return ["meal"]


def render_a8_banner_block(slug: str) -> str:
    keys = banner_keys_for_slug(slug)
    if not keys:
        return ""
    cards_list = []
    for key in keys:
        if key not in A8_BANNERS:
            continue
        detail = A8_BANNER_DETAILS.get(key, {})
        cards_list.append(
            '<article class="a8-banner-card"><div class="a8-banner-media">%s</div>'
            '<div class="a8-banner-copy"><h3>%s</h3><p>%s</p><dl>'
            '<div><dt>向いている人</dt><dd>%s</dd></div>'
            '<div><dt>申込み前の確認</dt><dd>%s</dd></div>'
            '</dl></div></article>' % (
                A8_BANNERS[key], html.escape(detail.get("title", "関連サービス")),
                html.escape(detail.get("description", "広告主ページでサービス内容と利用条件を確認してください。")),
                html.escape(detail.get("fit", "条件を比較して選びたい人")),
                html.escape(detail.get("check", "料金、対象条件、解約方法")),
            )
        )
    cards = "".join(cards_list)
    if not cards:
        return ""
    return '<aside class="a8-banner-section" aria-label="関連サービスの広告"><p class="a8-ad-label">PR・広告</p><h2>関連サービスの内容と条件</h2><p class="a8-banner-intro">バナーだけで判断せず、用途と申込み前の確認点を読んでから広告主ページへ進んでください。</p><div class="a8-banner-grid">%s</div><p class="a8-ad-note">料金・特典・提供条件は変更される場合があります。広告リンク先の最新情報を優先してください。</p></aside>' % cards
