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

    def get(self, lang: str, key_path: str, default: str = None, **kwargs) -> str:
        """
        Gets a translated string using dotted key paths (e.g. 'chat.button_regenerate').
        """
        # Fallback to English if the selected language is not loaded
        lang_data = self.locales.get(lang, self.locales.get("en", {}))
        
        keys = key_path.split('.')
        val = lang_data
        success = True
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                success = False
                break
                
        if success:
            if isinstance(val, str):
                if kwargs:
                    try:
                        return val.format(**kwargs)
                    except KeyError:
                        pass
                return val
            elif isinstance(val, dict):
                # If it's a dict, we might want a string but didn't specify the leaf key.
                # Fall through to recovery block in case there's a dot-separated flat key.
                pass

        # Recovery for dot-separated subcommand keys inside the 'commands' dict
        if len(keys) > 2 and keys[0] == "commands":
            commands_dict = lang_data.get("commands", {})
            if isinstance(commands_dict, dict):
                for i in range(len(keys) - 2, 0, -1):
                    cmd_name = ".".join(keys[1:1+i])
                    if cmd_name in commands_dict:
                        remaining_keys = keys[1+i:]
                        sub_val = commands_dict[cmd_name]
                        sub_success = True
                        for rk in remaining_keys:
                            if isinstance(sub_val, dict) and rk in sub_val:
                                sub_val = sub_val[rk]
                            else:
                                sub_success = False
                                break
                        if sub_success and isinstance(sub_val, str):
                            if kwargs:
                                try:
                                    return sub_val.format(**kwargs)
                                except KeyError:
                                    pass
                            return sub_val

        return key_path if default is None else default

i18n = I18nManager()
