from django.core.exceptions import ValidationError
from cities_light.models import Country, Region, City,SubRegion
import re

def validate_country(value):
    if not Country.objects.filter(id=value).exists():
        raise ValidationError(f'Invalid country ID: {value}')

def validate_region(value):
    if not Region.objects.filter(id=value).exists():
        raise ValidationError(f'Invalid region ID: {value}')
def validate_sub_region(value):
    if not SubRegion.objects.filter(id=value).exists():
        raise ValidationError(f'Invalid region ID: {value}')

def validate_city(value):
    if not City.objects.filter(id=value).exists():
        raise ValidationError(f'Invalid city ID: {value}')

def validate_region_belongs_to_country(region_id, country_id):
    if not Region.objects.filter(id=region_id, country_id=country_id).exists():
        raise ValidationError('The selected region does not belong to the selected country.')

def validate_sub_region_belongs_to_region(subregion_id, region_id):
    if not SubRegion.objects.filter(id=subregion_id, region_id=region_id).exists():
        raise ValidationError('The selected city does not belong to the selected region.')
def validate_city_belongs_to_sub_region(city_id, subregion_id,):
    if not City.objects.filter(id=city_id, subregion_id=subregion_id,).exists():
        raise ValidationError('The selected city does not belong to the selected region.')



def validate_postal_code(value):
    postal_code_pattern = r'^[A-Za-z0-9 -]{3,10}$'  # Example pattern, adjust as needed
    if not re.match(postal_code_pattern, value):
        raise ValidationError(f'Invalid postal code: {value}')

