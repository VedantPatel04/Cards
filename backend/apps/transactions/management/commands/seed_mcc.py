import json, os
from django.core.management.base import BaseCommand
from apps.transactions.models import MCC_Codes

TRAVEL_RANGES = [
    (3000, 3308),  # Airlines
    (3351, 3441),  # Car Rental Agencies
    (3501, 3835),  # Hotels, Motels, Resorts
]

CATEGORY_MAP = {
    # ── dining ──
    '5811': 'dining',
    '5812': 'dining',
    '5813': 'dining',
    '5814': 'dining',

    # ── groceries ──
    '5411': 'groceries',
    '5422': 'groceries',
    '5441': 'groceries',
    '5451': 'groceries',
    '5462': 'groceries',
    '5499': 'groceries',
    '5921': 'groceries',

    # ── travel (non-range codes) ──
    '4011': 'travel',
    '4111': 'travel',
    '4112': 'travel',
    '4119': 'travel',
    '4121': 'travel',
    '4131': 'travel',
    '4214': 'travel',
    '4215': 'travel',
    '4225': 'travel',
    '4411': 'travel',
    '4457': 'travel',
    '4468': 'travel',
    '4511': 'travel',
    '4582': 'travel',
    '4722': 'travel',
    '4723': 'travel',
    '4784': 'travel',
    '4789': 'travel',
    '7011': 'travel',
    '7012': 'travel',
    '7032': 'travel',
    '7033': 'travel',
    '7511': 'travel',
    '7512': 'travel',
    '7513': 'travel',
    '7519': 'travel',
    '7523': 'travel',

    # ── gas ──
    '5541': 'gas',
    '5542': 'gas',
    '5552': 'gas',
    '5983': 'gas',

    # ── entertainment ──
    '5735': 'entertainment',
    '5815': 'entertainment',
    '5816': 'entertainment',
    '5817': 'entertainment',
    '5818': 'entertainment',
    '7800': 'entertainment',
    '7801': 'entertainment',
    '7802': 'entertainment',
    '7829': 'entertainment',
    '7832': 'entertainment',
    '7841': 'entertainment',
    '7911': 'entertainment',
    '7922': 'entertainment',
    '7929': 'entertainment',
    '7932': 'entertainment',
    '7933': 'entertainment',
    '7941': 'entertainment',
    '7991': 'entertainment',
    '7992': 'entertainment',
    '7993': 'entertainment',
    '7994': 'entertainment',
    '7995': 'entertainment',
    '7996': 'entertainment',
    '7997': 'entertainment',
    '7998': 'entertainment',
    '7999': 'entertainment',
    '8412': 'entertainment',

    # ── shopping ──
    '5013': 'shopping',
    '5021': 'shopping',
    '5039': 'shopping',
    '5044': 'shopping',
    '5045': 'shopping',
    '5046': 'shopping',
    '5047': 'shopping',
    '5051': 'shopping',
    '5065': 'shopping',
    '5072': 'shopping',
    '5074': 'shopping',
    '5085': 'shopping',
    '5094': 'shopping',
    '5099': 'shopping',
    '5111': 'shopping',
    '5131': 'shopping',
    '5137': 'shopping',
    '5139': 'shopping',
    '5169': 'shopping',
    '5172': 'shopping',
    '5192': 'shopping',
    '5193': 'shopping',
    '5198': 'shopping',
    '5199': 'shopping',
    '5200': 'shopping',
    '5211': 'shopping',
    '5231': 'shopping',
    '5251': 'shopping',
    '5261': 'shopping',
    '5262': 'shopping',
    '5271': 'shopping',
    '5300': 'shopping',
    '5309': 'shopping',
    '5310': 'shopping',
    '5311': 'shopping',
    '5331': 'shopping',
    '5399': 'shopping',
    '5511': 'shopping',
    '5521': 'shopping',
    '5531': 'shopping',
    '5532': 'shopping',
    '5533': 'shopping',
    '5551': 'shopping',
    '5561': 'shopping',
    '5571': 'shopping',
    '5592': 'shopping',
    '5598': 'shopping',
    '5599': 'shopping',
    '5611': 'shopping',
    '5621': 'shopping',
    '5631': 'shopping',
    '5641': 'shopping',
    '5651': 'shopping',
    '5655': 'shopping',
    '5661': 'shopping',
    '5681': 'shopping',
    '5691': 'shopping',
    '5697': 'shopping',
    '5698': 'shopping',
    '5699': 'shopping',
    '5712': 'shopping',
    '5713': 'shopping',
    '5714': 'shopping',
    '5718': 'shopping',
    '5719': 'shopping',
    '5722': 'shopping',
    '5732': 'shopping',
    '5733': 'shopping',
    '5734': 'shopping',
    '5832': 'shopping',
    '5912': 'shopping',
    '5931': 'shopping',
    '5932': 'shopping',
    '5933': 'shopping',
    '5935': 'shopping',
    '5937': 'shopping',
    '5940': 'shopping',
    '5941': 'shopping',
    '5942': 'shopping',
    '5943': 'shopping',
    '5944': 'shopping',
    '5945': 'shopping',
    '5946': 'shopping',
    '5947': 'shopping',
    '5948': 'shopping',
    '5949': 'shopping',
    '5950': 'shopping',
    '5960': 'shopping',
    '5961': 'shopping',
    '5962': 'shopping',
    '5963': 'shopping',
    '5964': 'shopping',
    '5965': 'shopping',
    '5966': 'shopping',
    '5967': 'shopping',
    '5968': 'shopping',
    '5969': 'shopping',
    '5970': 'shopping',
    '5971': 'shopping',
    '5972': 'shopping',
    '5973': 'shopping',
    '5975': 'shopping',
    '5976': 'shopping',
    '5977': 'shopping',
    '5978': 'shopping',
    '5992': 'shopping',
    '5993': 'shopping',
    '5994': 'shopping',
    '5995': 'shopping',
    '5996': 'shopping',
    '5997': 'shopping',
    '5998': 'shopping',
    '5999': 'shopping',
}


def get_category(mcc_code): #associates merchant code from json file to category from CATEGORY_MAP
    code_int = int(mcc_code)
    for range_start, range_end in TRAVEL_RANGES:
        if range_start <= code_int <= range_end:
            return 'travel'
    return CATEGORY_MAP.get(mcc_code, 'other')


GENERIC_LABELS = {
    'Airlines', 'Car Rental', 'Hotels/Motels/Inns/Resorts',
}


def get_merchant_name(mcc_code, description):
    """
    Brand-specific MCC ranges (airlines, car rentals, hotels) carry the actual
    merchant name in their description (e.g. 'DELTA', 'MARRIOTT HOTELS').
    Codes whose description is just a generic fallback label (e.g. 'Airlines')
    are not specific merchants — leave merchant_name blank for those.
    """
    code_int = int(mcc_code)
    in_brand_range = any(rs <= code_int <= re for rs, re in TRAVEL_RANGES)
    if in_brand_range and description not in GENERIC_LABELS:
        return description
    return ''


class Command(BaseCommand):
    help =  "Maps MCC from mcc_category_map.json into the database"
    def handle(self, *args, **kwargs):
        mcc_file_path = os.path.join('data', 'card_catalog', 'mcc_codes.json')

        with open(mcc_file_path, 'r') as f:
            mcc_data = json.load(f) #load json file into mcc_data
        #tracks newly created mcc in MCC db table
        created_count = 0
        updated_count = 0

        for entry in mcc_data:
            category = get_category(entry['mcc'])
            merchant_name = get_merchant_name(entry['mcc'], entry['edited_description'])

            obj, created = MCC_Codes.objects.update_or_create(
                code=entry['mcc'],
                defaults={
                    'category': category,
                    'merchant_name': merchant_name,
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created_count} created, {updated_count} updated, '
            f'{len(mcc_data)} total processed.'
        ))