import json
import os
from typing import Dict, Any, Optional

class I18n:
    """多言語対応のためのユーティリティクラス"""
    
    _locales: Dict[str, Dict[str, str]] = {}
    _default_locale: str = "ja"
    
    @classmethod
    def load_locales(cls, locale_dir: str = "src/locales") -> None:
        """言語ファイルを読み込む"""
        cls._locales = {}
        
        # locale_dirからすべてのJSONファイルを読み込む
        try:
            for filename in os.listdir(locale_dir):
                if filename.endswith(".json"):
                    locale_code = filename.split(".")[0]
                    with open(f"{locale_dir}/{filename}", "r", encoding="utf-8") as f:
                        cls._locales[locale_code] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load locale files: {e}")
            # 最低限の日本語と英語を提供
            cls._locales = {
                "ja": {
                    "common.error": "エラーが発生しました",
                    "common.success": "成功しました",
                },
                "en": {
                    "common.error": "An error occurred",
                    "common.success": "Success",
                }
            }
    
    @classmethod
    def t(cls, key: str, locale: str = None, **kwargs) -> str:
        """指定されたキーの翻訳文字列を取得する
        
        Args:
            key: 翻訳キー（例: "commands.status.success"）
            locale: 言語コード（例: "ja", "en"）
            **kwargs: 翻訳文字列内の変数を置換するための引数
        
        Returns:
            翻訳された文字列。キーが見つからない場合はキー自体を返す。
        """
        if not cls._locales:
            cls.load_locales()
        
        # デフォルト言語を使用
        locale = locale or cls._default_locale
        
        # 指定された言語が存在しない場合はデフォルト言語を使用
        if locale not in cls._locales:
            locale = cls._default_locale
        
        # キーが存在する場合は翻訳を返す、存在しない場合はキー自体を返す
        translation = cls._locales[locale].get(key, key)
        
        # 変数置換処理
        for k, v in kwargs.items():
            translation = translation.replace(f"{{{k}}}", str(v))
        
        return translation
    
    @classmethod
    def set_default_locale(cls, locale: str) -> None:
        """デフォルト言語を設定する"""
        cls._default_locale = locale