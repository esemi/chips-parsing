from string import ascii_uppercase

VALID_CODE = 'TODO'
CODE_PREFIX = ''
DEBUG = False
CODE_CHARS = ascii_uppercase

URL = 'https://speaker.pringles.com/api/ru_RU/redemption/validate-codes'
MAX_CLIENTS = 500

try:
    from config_local import *
except ImportError:
    pass
