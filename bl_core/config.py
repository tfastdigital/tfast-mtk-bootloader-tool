import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = BASE_DIR / 'bin'
FASTBOOT_PATH = str(BIN_DIR / 'fastboot.exe')
WORKSPACE_DIR = BASE_DIR / 'workspace'
HANDOFF_DIR = BASE_DIR / 'handoff_secure'
PY314_RUNTIME_DIR = BASE_DIR / 'py314_runtime'
OFFLINE_REPO_DIR = BASE_DIR / 'offline_repo'

API_BASE_URL = 'https://smarttool.top/smarttool-api/index1.php'
MODEL_LIST_URL = 'https://smarttool.top/smarttool-api/bootloader.php?action=list'
DEDUCT_URL = 'https://smarttool.top/smarttool-api/bootloader.php?action=deduct'
PATCH_FILE_BASE = 'https://smarttool.top/smarttool-api/bootloader.php?action=file&name='
API_KEY_CLIENT = 'ST_CLIENT_9b72b728f79beb6edca63f47a836f50bc9b2989647a3c9f3ab8a1176c82347de'

DEFAULT_PATCH_COST = 4

FALLBACK_LOOKUP = {
    'Tecno Spark 40 Pro Plus (KM7)': {
        'id': 1,
        'codename': 'TECNO-KM7',
        'lk_a_filename': '1.bin',
        'lk_b_filename': '1a.bin',
        'patch_cost': 4,
        'brand': 'Tecno',
        'model': 'Spark 40 Pro Plus (KM7)'
    },
    'Tecno Camon 40 (CM5)': {
        'id': 2,
        'codename': 'TECNO-CM5',
        'lk_a_filename': '2.bin',
        'lk_b_filename': '2a.bin',
        'patch_cost': 4,
        'brand': 'Tecno',
        'model': 'Camon 40 (CM5)'
    },
    'Tecno Camon 40 Pro (CM6)': {
        'id': 3,
        'codename': 'TECNO-CM6',
        'lk_a_filename': '3.bin',
        'lk_b_filename': '3a.bin',
        'patch_cost': 4,
        'brand': 'Tecno',
        'model': 'Camon 40 Pro (CM6)'
    }
}

FALLBACK_MODELS = list(FALLBACK_LOOKUP.keys())

# Transsion anti-tamper / guard overlays. These are OEM bookkeeping partitions
# that re-arm verification; erasing them is the intended, safe operation.
TRASH_PARTITIONS = (
    'tr_product',
    'tr_vendor',
    'tr_system',
)

# Transsion anti-tamper / guard overlays. These are OEM bookkeeping partitions
# that re-arm verification; erasing them is the intended, safe operation.
TRASH_PARTITIONS = (
    'tr_product',
    'tr_vendor',
    'tr_system',
)

#: Real system partitions that the Transsion flow also clears **after** the
#: bootloader has been unlocked, because the guard overlays point back at them.
#: Erasing these requires an unlocked bootloader (the stock LK gates the write
#: otherwise) and the device will not boot again until firmware is reflashed.
EXTRA_SYSTEM_PARTITIONS = (
    'product',
    'system_ext',
)

#: The full guard wipe set used on an unlocked device.
GUARD_WIPE_PARTITIONS = TRASH_PARTITIONS + EXTRA_SYSTEM_PARTITIONS

AVB_MAGIC = b'AVB0'
AVB_HEADER_SIZE = 256
AVB_FLAGS_OFFSET = 120
AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED = 0x01
AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED = 0x02
AVB_DISABLE_ALL_FLAGS = AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED | AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED
