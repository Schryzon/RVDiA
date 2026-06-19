import os
import json

class I18nManager:
    def __init__(self):
        self.locales = {}
        # Load locales from root locales/ directory
        locales_dir = os.path.join(os.path.dirname(__file__), '../../locales')
        if os.path.exists(locales_dir):
            for filename in os.listdir(locales_dir):
                if filename.endswith('.json'):
                    lang_code = filename[:-5]
                    with open(os.path.join(locales_dir, filename), 'r', encoding='utf-8') as f:
                        self.locales[lang_code] = json.load(f)

    def get(self, lang: str, key_path: str, default: str = "", **kwargs) -> str:
        """
        Gets a translated string using dotted key paths (e.g. 'chat.button_regenerate').
        """
        # Fallback to English if the selected language is not loaded
        lang_data = self.locales.get(lang, self.locales.get("en", {}))
        
        keys = key_path.split('.')
        val = lang_data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default or key_path
                
        if isinstance(val, str):
            if kwargs:
                try:
                    return val.format(**kwargs)
                except KeyError:
                    pass
            return val
        return default or key_path

i18n = I18nManager()
