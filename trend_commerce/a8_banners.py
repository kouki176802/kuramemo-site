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
    if "internet" in slug or "carrier" in slug or slug == "category-services":
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
    cards = "".join('<div class="a8-banner-card">%s</div>' % A8_BANNERS[key] for key in keys if key in A8_BANNERS)
    if not cards:
        return ""
    return '<aside class="a8-banner-section" aria-label="おすすめ広告"><p class="a8-ad-label">PR・広告</p><h2>関連サービスを確認</h2><div class="a8-banner-grid">%s</div><p class="a8-ad-note">広告リンク先で最新の料金・条件を確認してください</p></aside>' % cards
