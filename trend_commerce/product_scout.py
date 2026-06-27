from __future__ import annotations

import csv
import math
import time
import urllib.error
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .catalog import import_offers, upsert_offer_csv
from .rakuten import RakutenProduct, RakutenProductClient
from .settings import ROOT, Settings


@dataclass(frozen=True)
class ProductCandidate:
    page_slug: str
    offer_id: str
    product_group: str
    keyword: str
    category: str
    name: str
    score: int
    min_price: int
    max_price: int
    review_count: int
    review_average: float
    product_url: str
    affiliate_url: str
    image_url: str
    shop_name: str
    reasons: List[str]


def score_rakuten_product(product: RakutenProduct, keyword: str, product_group: str = "") -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    name = product.name.lower()
    terms = [term.strip().lower() for term in keyword.replace("　", " ").split() if term.strip()]
    group_terms = [term.strip().lower() for term in product_group.replace("・", " ").replace("　", " ").split() if term.strip()]

    if product.affiliate_url:
        score += 18
        reasons.append("アフィリエイトURLあり")
    if product.availability == 1:
        score += 18
        reasons.append("販売中")
    elif product.availability == 0 and product.product_id and ":" in product.product_id:
        score -= 40
        reasons.append("販売状況不明/販売終了の可能性")
    if product.min_price > 0:
        score += 10
        reasons.append("価格取得あり")
        if _target_price_min(product_group) <= product.min_price <= _target_price_max(product_group):
            score += 10
            reasons.append("需要に合いやすい価格帯")
        elif product.min_price > 30000:
            score -= 10
            reasons.append("高価格で初回導線には重い")
    if product.review_count:
        score += min(24, int(math.log10(product.review_count + 1) * 10))
        reasons.append("レビュー数:%d" % product.review_count)
        if product.review_count < 10:
            score -= 18
            reasons.append("レビュー件数が少なく初期掲載は慎重")
    else:
        score -= 15
        reasons.append("レビュー不足")
    if product.review_average:
        score += int((product.review_average / 5) * 18)
        reasons.append("レビュー平均:%.2f" % product.review_average)
        if product.review_average < 3.5 and product.review_count >= 3:
            score -= 18
            reasons.append("評価が低め")
        elif product.review_average >= 4.0 and product.review_count >= 10:
            score += 8
            reasons.append("評価とレビュー数の両立")
    if product.postage_flag == 0 and product.product_id and ":" in product.product_id:
        score += 4
        reasons.append("送料込み/送料無料")
    if product.shop_of_the_year == 1:
        score += 5
        reasons.append("Shop of the Year店舗")
    matched_terms = [term for term in terms + group_terms if term and term in name]
    if matched_terms:
        score += min(20, len(set(matched_terms)) * 8)
        reasons.append("商品名一致:%s" % "/".join(sorted(set(matched_terms))[:3]))
    if "中古" in product.name or "訳あり" in product.name:
        score -= 20
        reasons.append("中古/訳ありは初期導線から除外寄り")
    penalty = _product_group_mismatch_penalty(product.name, product_group)
    if penalty:
        score -= penalty
        reasons.append("商品タイプ不一致の可能性")
    return max(0, min(score, 100)), reasons


def _target_price_min(product_group: str) -> int:
    if any(term in product_group for term in ["炊飯器", "電子レンジ", "掃除機", "空気清浄機", "ヒーター"]):
        return 3000
    if any(term in product_group for term in ["電気ケトル", "トースター", "ミキサー", "ドライヤー", "扇風機"]):
        return 1500
    if "充電器" in product_group:
        return 1000
    if "モバイルバッテリー" in product_group:
        return 1500
    if "スキンケア" in product_group or "洗顔" in product_group or "保湿" in product_group or "オールインワン" in product_group or "リップケア" in product_group:
        return 700
    if "トレーニング" in product_group or "プロテイン" in product_group:
        return 900
    if any(term in product_group for term in ["クレアチン", "EAA", "BCAA", "グルタミン", "ビタミン", "食物繊維", "乳酸菌", "カルシウム"]):
        return 700
    if any(term in product_group for term in ["脱毛器", "シェーバー", "トリマー", "ヘアアイロン"]):
        return 2000
    if "ヘアワックス" in product_group:
        return 500
    if "サーキュレーター" in product_group:
        return 3000
    if "冷感寝具" in product_group:
        return 1500
    return 800


def _target_price_max(product_group: str) -> int:
    if any(term in product_group for term in ["炊飯器", "電子レンジ", "掃除機", "空気清浄機"]):
        return 50000
    if any(term in product_group for term in ["電気ケトル", "トースター", "ミキサー", "ドライヤー", "扇風機", "ヒーター"]):
        return 25000
    if "充電器" in product_group:
        return 9000
    if "モバイルバッテリー" in product_group:
        return 16000
    if "スキンケア" in product_group or "洗顔" in product_group or "保湿" in product_group or "オールインワン" in product_group or "リップケア" in product_group:
        return 8000
    if "トレーニング" in product_group or "プロテイン" in product_group:
        return 12000
    if any(term in product_group for term in ["クレアチン", "EAA", "BCAA", "グルタミン", "ビタミン", "食物繊維", "乳酸菌", "カルシウム"]):
        return 15000
    if any(term in product_group for term in ["脱毛器", "シェーバー", "トリマー", "ヘアアイロン"]):
        return 60000
    if "ヘアワックス" in product_group:
        return 6000
    if "サーキュレーター" in product_group:
        return 18000
    if "冷感寝具" in product_group:
        return 12000
    return 9000


def _product_group_mismatch_penalty(product_name: str, product_group: str) -> int:
    name = product_name.lower()
    rules = {
        "サーキュレーター": ["ソックス", "着圧", "靴下", "タイツ", "ストッキング"],
        "携帯扇風機": ["ディズニー", "おもちゃ", "玩具"],
        "冷感寝具": ["ペット", "犬用", "猫用", "猫犬", "犬猫"],
        "小型USB-C充電器": ["ケーブル単品", "ケーブルのみ", "コードのみ"],
        "モバイルバッテリー": ["ケース", "ポーチ", "ケーブルのみ", "フィルム"],
        "プロテイン": ["小魚", "アーモンド", "おやつ", "スイーツ", "バー", "雑炊", "置き換え", "低糖質", "糖質制限", "ダイエット食品", "ジュニア", "子供", "子ども", "こども", "キッズ", "小学生", "中学生"],
        "メンズ洗顔料": ["レディース", "女性用"],
        "メンズ保湿アイテム": ["レディース", "女性用", "サンプル", "お試し", "洗顔", "石鹸", "石けん", "せっけん"],
        "メンズ日焼け止め": ["アームカバー", "アームガード", "ラッシュガード", "ウェア", "帽子", "サングラス", "手袋", "ハンドウォーマー", "防寒"],
    }
    for group, bad_terms in rules.items():
        if group in product_group and any(term.lower() in name for term in bad_terms):
            return 45
    if "小型USB-C充電器" in product_group:
        charger_terms = ["acアダプ", "ac アダプ", "アダプター", "アダプタ", "コンセント", "gan", "pse", "pd充電器", "usb充電器", "折りたたみ"]
        if "ケーブル" in product_name and not any(term in name for term in charger_terms):
            return 55
        if ("充電ケーブル" in product_name or "充電コード" in product_name) and not any(term in name for term in charger_terms):
            return 70
    if "多ポート充電器" in product_group:
        if "車載" in product_name or "シガーソケット" in product_name:
            return 35
        if "usbハブ" in name and "充電器" not in product_name:
            return 45
    if "モバイルバッテリー" in product_group:
        battery_terms = ["モバイルバッテリー", "バッテリー", "power bank", "powerbank"]
        if not any(term in name for term in battery_terms):
            return 65
        if "ケーブル" in product_name and not any(term in name for term in battery_terms):
            return 65
    if "大容量モバイルバッテリー" in product_group:
        capacity_terms = ["10000mah", "15000mah", "20000mah", "30000mah", "大容量"]
        small_capacity_terms = ["3000mah", "5000mah", "5200mah", "6000mah"]
        if any(term in name for term in small_capacity_terms):
            return 75
        if not any(term in name for term in capacity_terms):
            return 55
    if "高出力モバイルバッテリー" in product_group:
        output_terms = ["pd", "20w", "22.5w", "30w", "45w", "60w", "65w", "高出力", "急速充電"]
        if not any(term in name for term in output_terms):
            return 45
    if "MagSafe対応バッテリー" in product_group:
        magsafe_terms = ["magsafe", "mag-safe", "マグセーフ", "ワイヤレス", "磁気", "マグネット"]
        if not any(term in name for term in magsafe_terms):
            return 55
    if "プロテイン" in product_group:
        protein_terms = ["プロテイン", "ホエイ", "ソイ", "wpi", "wpc", "粉末"]
        if not any(term in name for term in protein_terms):
            return 65
        powder_terms = ["ホエイ", "ソイ", "wpi", "wpc", "粉末", "kg", "キロ", "シェイカー"]
        if not any(term in name for term in powder_terms):
            return 45
    if "メンズ" in product_group:
        mens_terms = ["メンズ", "男性", "男"]
        if not any(term in product_name for term in mens_terms):
            return 35
    if "日焼け止め" in product_group:
        sunscreen_terms = ["日焼け止め", "spf", "pa++++", "pa+++"]
        wearable_terms = ["パーカー", "ラッシュガード", "アームカバー", "帽子", "サングラス", "手袋", "マスク", "ウェア", "bbクリーム", "ファンデーション"]
        if any(term in name for term in wearable_terms):
            return 95
        if not any(term in name for term in sunscreen_terms):
            return 65
    if "保湿アイテム" in product_group:
        moisturizer_terms = ["化粧水", "乳液", "クリーム", "オールインワン", "ローション", "ジェル", "保湿液", "美容液"]
        if "オールインワン" in product_name:
            return 70
        if not any(term in product_name for term in moisturizer_terms):
            return 65
    if "オールインワン" in product_group:
        if any(term in product_name for term in ["お試し", "サンプル", "試供品", "トライアル", "シートマスク", "フェイスマスク", "シートパック", "フェイスパック", "パック"]):
            return 85
        if "オールインワン" not in product_name:
            return 75
    if "リップケア" in product_group:
        if any(term in product_name for term in ["化粧品原料", "手作り", "材料", "シアバター・精製"]):
            return 90
        if not any(term in product_name for term in ["リップクリーム", "リップバーム", "リップケア", "薬用リップ"]):
            return 75
    if "USB-Cケーブル" in product_group:
        if "アダプター" in product_name and "ケーブル" not in product_name:
            return 45
    if "可変式ダンベル" in product_group:
        adjustable_terms = ["可変式", "可変", "アジャスタブル", "重量調整", "調整式"]
        accessory_terms = ["グリップテープ", "テープ", "グローブ", "ラック", "シャフトのみ", "プレートのみ", "カラー", "クリップ"]
        if any(term in product_name for term in accessory_terms):
            return 80
        if not any(term in product_name for term in adjustable_terms):
            return 70
        if "ダンベル" not in product_name:
            return 65
    if "フォームローラー" in product_group:
        roller_terms = ["フォームローラー", "筋膜ローラー", "ストレッチローラー", "ヨガポール"]
        if "ヨガマット" in product_name:
            return 95
        if not any(term in product_name for term in roller_terms):
            return 60
    if "充電ステーション" in product_group:
        station_terms = ["ステーション", "スタンド", "4台", "5台", "6台", "複数", "同時充電", "収納"]
        if not any(term in product_name for term in station_terms):
            return 50
    if "ワイヤレス充電器" in product_group:
        wireless_terms = ["ワイヤレス", "magsafe", "mag-safe", "qi", "マグネット"]
        if not any(term in name for term in wireless_terms):
            return 55
    if "ロボット掃除機" in product_group:
        vacuum_terms = ["ロボット掃除機", "お掃除ロボット", "ロボットクリーナー", "掃除ロボット"]
        accessory_terms = ["滑り止め", "すべり止め", "フィルター", "ブラシ", "紙パック", "バッテリー", "交換用", "消耗品", "テレビスタンド", "テレビ台", "家具", "チェア", "椅子", "イス", "テーブル"]
        if any(term in product_name for term in accessory_terms):
            return 95
        if "対応" in product_name and not any(term in product_name for term in ["ロボット掃除機", "ロボットクリーナー", "掃除ロボット"]):
            return 95
        if not any(term in product_name for term in vacuum_terms):
            return 85
    if "衣類スチーマー" in product_group:
        steamer_terms = ["衣類スチーマー", "ハンディスチーマー", "スチームアイロン", "ハンガースチーマー"]
        accessory_terms = ["アイロンマット", "アイロン台", "収納", "シート", "カバー"]
        if any(term in product_name for term in accessory_terms) and not any(term in product_name for term in steamer_terms):
            return 95
        if not any(term in product_name for term in steamer_terms):
            return 80
    if "電気圧力鍋" in product_group:
        cooker_terms = ["電気圧力鍋", "自動調理鍋", "圧力鍋", "電気鍋"]
        if not any(term in product_name for term in cooker_terms):
            return 80
    if "布団乾燥機" in product_group:
        dryer_terms = ["布団乾燥機", "ふとん乾燥機"]
        if not any(term in product_name for term in dryer_terms):
            return 75
    if "除湿機・部屋干し" in product_group:
        dehumidifier_terms = ["除湿機", "除湿器", "衣類乾燥除湿機", "衣類乾燥機"]
        accessory_terms = ["除菌液", "消臭", "スプレー", "洗剤", "ハンガー", "物干し", "ラック"]
        if any(term in product_name for term in accessory_terms) and not any(term in product_name for term in dehumidifier_terms):
            return 95
        if not any(term in product_name for term in dehumidifier_terms):
            return 80
    if "ポータブル電源" in product_group:
        power_station_terms = ["ポータブル電源", "蓄電池", "発電機", "wh", "w出力", "ac出力", "リン酸鉄"]
        small_battery_terms = ["4000mah", "5000mah", "6000mah", "モバイルバッテリー", "スマホ充電器", "携帯充電器"]
        solar_panel_terms = ["ソーラーパネル", "ソーラーチャージャー", "ソーラー充電器"]
        if any(term in name for term in small_battery_terms) and not any(term in name for term in power_station_terms):
            return 90
        if any(term in name for term in solar_panel_terms) and not any(term in name for term in ["wh", "蓄電池", "ポータブルバッテリー", "ac出力"]):
            return 80
        if not any(term in name for term in power_station_terms):
            return 70
    if "非常食セット" in product_group:
        food_terms = ["非常食セット", "防災食セット", "保存食セット", "アルファ米", "尾西", "長期保存", "5年保存", "7年保存", "備蓄セット"]
        snack_terms = ["佃煮", "おつまみ", "お試し", "ラーメン", "ご飯のお供", "メール便", "味噌汁", "みそ汁", "仕送り"]
        light_food_terms = ["スープ", "水 保存水", "備蓄水", "お菓子", "ようかん"]
        if any(term in product_name for term in snack_terms) and not any(term in product_name for term in food_terms):
            return 95
        if any(term in product_name for term in light_food_terms) and not any(term in product_name for term in ["アルファ米", "尾西", "非常食セット", "防災食セット", "3日分", "ご飯"]):
            return 70
        if not any(term in product_name for term in food_terms):
            return 85
    if "防災リュック" in product_group:
        set_terms = ["防災リュック", "非常持ち出し", "非常用持ち出し", "避難リュック", "防災バッグ", "防災リュックセット"]
        must_terms = ["リュック", "バッグ", "持ち出し", "避難袋"]
        wrong_terms = ["トイレ", "眼鏡", "めがね", "メガネ", "食品", "非常食", "保存食", "水", "ライト", "ラジオ"]
        if any(term in product_name for term in wrong_terms) and not any(term in product_name for term in ["防災リュック", "防災バッグ", "避難リュック"]):
            return 95
        if not any(term in product_name for term in set_terms):
            return 85
        if not any(term in product_name for term in must_terms):
            return 90
        if "リュックのみ" in product_name or "/のみ" in product_name:
            return 70
    if "防災ランタン・ラジオ" in product_group:
        light_radio_terms = ["ランタン", "ラジオ", "防災ライト", "ledライト", "手回し"]
        if not any(term in name for term in light_radio_terms):
            return 60
    if "スーツケース" in product_group:
        suitcase_terms = ["スーツケース", "キャリーケース", "キャリーバッグ"]
        accessory_terms = ["ベルト", "カバー", "キャスターカバー", "ネームタグ", "南京錠", "鍵", "ロック"]
        if any(term in product_name for term in accessory_terms) and not any(term in product_name for term in ["スーツケース本体", "キャリーケース"]):
            return 95
        if not any(term in product_name for term in suitcase_terms):
            return 85
    if "セキュリティポーチ" in product_group:
        pouch_terms = ["セキュリティポーチ", "貴重品ポーチ", "パスポートケース", "パスポートポーチ", "トラベルポーチ"]
        accessory_terms = ["カード", "スキミング防止カード", "シート", "財布のみ"]
        if any(term in product_name for term in accessory_terms) and not any(term in product_name for term in pouch_terms):
            return 95
        if not any(term in product_name for term in pouch_terms):
            return 80
    if "トラベル充電器" in product_group:
        charger_terms = ["充電器", "acアダプ", "アダプター", "アダプタ", "変換プラグ", "トラベルアダプター", "電源タップ"]
        cable_only_terms = ["ケーブル", "コード"]
        if any(term in product_name for term in cable_only_terms) and not any(term in product_name for term in ["acアダプ", "アダプター", "アダプタ", "変換プラグ", "電源タップ", "コンセント"]):
            return 90
        if not any(term in product_name for term in charger_terms):
            return 80
    if "空気清浄機" in product_group:
        wrong_terms = ["次亜塩素酸水", "除菌スプレー", "消臭スプレー", "虫よけ", "害虫対策", "サーキュレーター", "扇風機"]
        if any(term in product_name for term in wrong_terms):
            return 95
        if "加湿器" in product_name and "加湿空気清浄機" not in product_name:
            return 90
    if "ワイヤレスマウス" in product_group:
        if any(term in name for term in ["マウスパッド", "ケース", "レシーバーのみ", "交換用", "部品"]):
            return 95
        if "マウス" not in product_name:
            return 85
    if "PCキーボード" in product_group:
        if any(term in name for term in ["キーキャップ", "キースイッチ", "キーボードカバー", "交換用", "部品", "リサイクル", "回収", "処分", "廃棄"]):
            return 95
        if "キーボード" not in product_name:
            return 85
    if "USB-Cハブ" in product_group:
        if any(term in name for term in ["ケーブルのみ", "変換アダプタのみ", "延長ケーブル"]):
            return 90
        if not any(term in name for term in ["usb-cハブ", "usb c ハブ", "type-cハブ", "type c ハブ", "ドッキングステーション"]):
            return 80
    if "ノートPCスタンド" in product_group:
        if any(term in name for term in ["スマホスタンド", "タブレットスタンド", "車載", "モニターアーム"]):
            return 95
        if not any(term in name for term in ["ノートpcスタンド", "ノートパソコンスタンド", "パソコンスタンド"]):
            return 80
    if "Webカメラ" in product_group:
        if any(term in name for term in ["防犯カメラ", "監視カメラ", "ペットカメラ", "屋外カメラ", "ノートパソコン", "ノートpc", "デスクトップpc"]):
            return 95
        if not any(term in name for term in ["webカメラ", "ウェブカメラ", "pcカメラ"]):
            return 85
    if product_group == "扇風機":
        if any(term in product_name for term in ["卓上", "クリップ", "ハンディ", "携帯"]):
            return 95
        if "サーキュレーター" in product_name and not any(term in product_name for term in ["リビング扇風機", "リビングファン", "dc扇風機"]):
            return 80
    if product_group == "炊飯器":
        if any(term in product_name for term in ["土鍋", "ごはん鍋", "ご飯鍋", "炊飯釜", "玄米炊飯セット", "電気圧力鍋"]):
            return 95
    appliance_rules = {
        "炊飯器": (["炊飯器"], ["内釜", "ふた", "パッキン", "交換用", "部品", "しゃもじ"]),
        "電子レンジ": (["電子レンジ", "オーブンレンジ"], ["プレート", "皿", "カバー", "ラック", "容器", "調理器"]),
        "電気ケトル": (["電気ケトル", "電気ポット"], ["洗浄剤", "クエン酸", "カバー", "部品"]),
        "オーブントースター": (["トースター", "オーブントースター"], ["受け皿", "トレー", "網", "カバー", "部品"]),
        "ミキサー": (["ミキサー", "ブレンダー"], ["ボトルのみ", "容器のみ", "替刃", "交換用", "部品"]),
        "コードレス掃除機": (["コードレス掃除機", "スティック掃除機", "クリーナー"], ["フィルター", "バッテリー", "ヘッド", "ブラシ", "スタンドのみ", "交換用", "部品"]),
        "空気清浄機": (["空気清浄機", "加湿空気清浄機"], ["フィルター", "交換用", "集じん", "脱臭フィルタ", "部品"]),
        "ドライヤー": (["ドライヤー", "ヘアドライヤー"], ["ホルダー", "スタンド", "収納", "ノズルのみ"]),
        "扇風機": (["扇風機", "リビングファン"], ["カバー", "収納袋", "羽根", "リモコンのみ", "卓上", "携帯"]),
        "セラミックヒーター": (["セラミックヒーター", "ファンヒーター"], ["フィルター", "ガード", "カバー", "部品"]),
    }
    for group, (required, accessories) in appliance_rules.items():
        if group not in product_group:
            continue
        if any(term in product_name for term in accessories) and not any(term in product_name for term in required):
            return 95
        if not any(term in product_name for term in required):
            return 85
    required_terms = {
        "ヘアワックス": ["ワックス", "スタイリング"],
        "家庭用脱毛器": ["脱毛器", "光美容器"],
        "電気シェーバー": ["シェーバー", "髭剃り", "ひげそり"],
        "ボディトリマー": ["ボディトリマー", "グルーマー", "全身トリマー"],
        "ヘアアイロン": ["ヘアアイロン", "ストレートアイロン"],
        "クレアチン": ["クレアチン", "creatine"],
        "EAA": ["eaa", "必須アミノ酸"],
        "BCAA": ["bcaa", "分岐鎖アミノ酸"],
        "グルタミン": ["グルタミン", "glutamine"],
        "マルチビタミン": ["マルチビタミン", "マルチ ビタミン"],
        "ビタミンC": ["ビタミンc", "vitamin c"],
        "食物繊維": ["食物繊維", "デキストリン", "イヌリン"],
        "乳酸菌": ["乳酸菌", "ビフィズス菌"],
        "カルシウム・マグネシウム": ["カルシウム", "マグネシウム", "カルマグ"],
    }
    for group, terms in required_terms.items():
        if group in product_group and not any(term in name for term in terms):
            return 75
    if product_group == "ビタミンC" and any(term in product_name for term in ["マルチビタミン", "コンブチャ", "乳酸菌", "青汁"]):
        return 90
    if product_group == "BCAA" and "eaa" in name and "bcaa" not in name:
        return 90
    if product_group == "EAA" and "bcaa" in name and "eaa" not in name:
        return 90
    if "電気シェーバー" in product_group:
        if any(term in name for term in ["レディース", "女性用", "vio", "ヒートカッター", "アンダーヘア"]):
            return 95
        if not any(term in name for term in ["髭", "ひげ", "メンズシェーバー", "電気シェーバー"]):
            return 80
    if "食物繊維" in product_group:
        if any(term in name for term in ["おからパウダー", "小麦粉", "クッキー", "パン", "ドーナツ"]):
            return 90
        if not any(term in name for term in ["デキストリン", "イヌリン", "食物繊維 サプリ", "食物繊維パウダー"]):
            return 75
    return 0


def scout_page_products(
    settings: Settings,
    page_slug: str,
    limit_per_keyword: int = 5,
    queries_per_group: int = 2,
    delay_seconds: float = 1.5,
    live_items: bool = True,
    client: Optional[RakutenProductClient] = None,
) -> List[ProductCandidate]:
    client = client or RakutenProductClient()
    rows = [row for row in _load_map_rows() if row["page_slug"] == page_slug]
    candidates: List[ProductCandidate] = []
    seen: set[str] = set()
    for row in rows:
        if live_items and "rakuten_jp" not in row.get("affiliate_priority", ""):
            continue
        keywords = [kw.strip() for kw in row["search_keywords"].split("|") if kw.strip()]
        for keyword in keywords[: max(1, queries_per_group)]:
            products = _safe_search(client, keyword, limit_per_keyword, live_items=live_items)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            for product in products:
                dedupe_key = product.product_id or product.product_url or product.name
                scoped_key = "%s:%s" % (row["offer_candidate_id"], dedupe_key)
                if scoped_key in seen:
                    continue
                seen.add(scoped_key)
                score, reasons = score_rakuten_product(product, keyword, row["product_group"])
                candidates.append(
                    ProductCandidate(
                        page_slug=page_slug,
                        offer_id=row["offer_candidate_id"],
                        product_group=row["product_group"],
                        keyword=keyword,
                        category=row["category"],
                        name=product.name,
                        score=score,
                        min_price=product.min_price,
                        max_price=product.max_price,
                        review_count=product.review_count,
                        review_average=product.review_average,
                        product_url=product.product_url,
                        affiliate_url=product.affiliate_url,
                        image_url=product.image_url,
                        shop_name=product.shop_name,
                        reasons=reasons,
                    )
                )
    candidates.sort(key=lambda item: (-item.score, item.offer_id, item.min_price or 999999, item.name))
    return candidates


def _safe_search(client: RakutenProductClient, keyword: str, limit: int, live_items: bool = True) -> List[RakutenProduct]:
    try:
        return client.search_items(keyword, limit=limit) if live_items else client.search(keyword, limit=limit)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            time.sleep(5)
            try:
                return client.search_items(keyword, limit=limit) if live_items else client.search(keyword, limit=limit)
            except urllib.error.HTTPError:
                return []
        return []


def best_by_offer(candidates: Iterable[ProductCandidate]) -> List[ProductCandidate]:
    best: Dict[str, ProductCandidate] = {}
    for candidate in candidates:
        current = best.get(candidate.offer_id)
        if current is None or candidate.score > current.score:
            best[candidate.offer_id] = candidate
    return sorted(best.values(), key=lambda item: (item.page_slug, item.offer_id))


def best_publishable_by_offer(candidates: Iterable[ProductCandidate]) -> List[ProductCandidate]:
    """Choose commercially usable candidates, preferring quality over low price."""
    eligible = [
        item for item in candidates
        if item.affiliate_url
        and item.score >= 75
        and item.review_count >= 20
        and item.review_average >= 4.0
        and "商品タイプ不一致の可能性" not in item.reasons
    ]
    pools: Dict[tuple[str, str], List[ProductCandidate]] = {}
    for candidate in eligible:
        pools.setdefault((candidate.page_slug, candidate.offer_id), []).append(candidate)
    for pool in pools.values():
        pool.sort(key=lambda item: (-_candidate_quality(item), item.min_price or 999999, item.name))
    selected: List[ProductCandidate] = []
    used_by_page: Dict[str, set[str]] = {}
    for (page_slug, offer_id) in sorted(pools):
        used = used_by_page.setdefault(page_slug, set())
        for candidate in pools[(page_slug, offer_id)]:
            product_key = candidate.product_url or candidate.affiliate_url or candidate.name
            if product_key in used:
                continue
            used.add(product_key)
            selected.append(candidate)
            break
    return selected


def _candidate_quality(candidate: ProductCandidate) -> float:
    return candidate.score + candidate.review_average * 5 + min(20, math.log10(candidate.review_count + 1) * 5)


def write_candidates_csv(candidates: List[ProductCandidate], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "page_slug", "offer_id", "product_group", "keyword", "category", "name", "score",
        "min_price", "max_price", "review_count", "review_average", "has_affiliate_url",
        "product_url", "affiliate_url", "image_url", "shop_name", "reasons",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({
                "page_slug": candidate.page_slug,
                "offer_id": candidate.offer_id,
                "product_group": candidate.product_group,
                "keyword": candidate.keyword,
                "category": candidate.category,
                "name": candidate.name,
                "score": candidate.score,
                "min_price": candidate.min_price,
                "max_price": candidate.max_price,
                "review_count": candidate.review_count,
                "review_average": candidate.review_average,
                "has_affiliate_url": bool(candidate.affiliate_url),
                "product_url": candidate.product_url,
                "affiliate_url": candidate.affiliate_url,
                "image_url": candidate.image_url,
                "shop_name": candidate.shop_name,
                "reasons": "|".join(candidate.reasons),
            })


def activate_candidates(settings: Settings, candidates: List[ProductCandidate]) -> int:
    activated = 0
    today = date.today().isoformat()
    for candidate in best_publishable_by_offer(candidates):
        if not candidate.affiliate_url:
            continue
        upsert_offer_csv({
            "offer_id": candidate.offer_id,
            "network": "rakuten",
            "name": candidate.name,
            "category": candidate.category,
            "keywords": "%s|%s|%s" % (candidate.product_group, candidate.keyword, candidate.name),
            "problem_tags": candidate.product_group,
            "event_tags": candidate.keyword,
            "affiliate_url": candidate.affiliate_url,
            "landing_url": candidate.product_url,
            "reward_type": "percent",
            "reward_value": "0",
            "allowed_media": "site|x|instagram",
            "status": "active",
            "last_verified_at": today,
        })
        _upsert_offer_asset_csv(candidate)
        activated += 1
    if activated:
        import_offers(settings)
    return activated


def _load_map_rows() -> List[Dict[str, str]]:
    path = ROOT / "data" / "comparison_product_map.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _upsert_offer_asset_csv(candidate: ProductCandidate) -> None:
    path = ROOT / "data" / "offer_assets.csv"
    fields = [
        "offer_id", "image_url", "shop_name", "min_price", "review_count",
        "review_average", "score", "updated_at",
    ]
    rows: List[Dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    row = {
        "offer_id": candidate.offer_id,
        "image_url": candidate.image_url,
        "shop_name": candidate.shop_name,
        "min_price": str(candidate.min_price),
        "review_count": str(candidate.review_count),
        "review_average": str(candidate.review_average),
        "score": str(candidate.score),
        "updated_at": date.today().isoformat(),
    }
    replaced = False
    for index, existing in enumerate(rows):
        if existing.get("offer_id") == candidate.offer_id:
            rows[index] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
