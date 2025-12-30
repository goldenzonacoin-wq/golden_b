# app/management/commands/import_nigeria.py
import csv
from django.core.management.base import BaseCommand
from cities_light.models import Country, Region, SubRegion, City

class Command(BaseCommand):
    help = 'Import Nigerian cities from custom text file'
    

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the Nigeria cities text file')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        country, _ = Country.objects.get_or_create(code2='NG')

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            
            for row in reader:
                try:
                    # Parse columns based on your model structure
                    geoname_id = int(row[0])
                    name = row[1]
                    name_ascii = row[2]  # Matches Base.name_ascii
                    alt_names = row[3] if row[3] else ''
                    lat = float(row[4])
                    lng = float(row[5])
                    admin1_code = row[10]  # State code
                    admin2_code = row[11]  # LGA code
                    population = int(row[14]) if row[14] else None
                    timezone = row[17]
                    feature_code = row[7]

                    try:
                        region= Region.objects.get(
                            country=country,
                            geoname_code=admin1_code,
                            
                        )
                    except Region.DoesNotExist:
                        self.stdout.write(f'Region not found: {admin1_code}')
                        continue
                    
                    try:

                        subregion= SubRegion.objects.get(
                            region=region,
                            geoname_code=admin2_code,
                            
                        )

                    except SubRegion.DoesNotExist:
                        subregion=None

                    City.objects.update_or_create(
                        geoname_id=geoname_id,
                        defaults={
                            'name': name,
                            'name_ascii': name_ascii,
                            'alternate_names': alt_names,
                            'latitude': lat,
                            'longitude': lng,
                            'country': country,
                            'region': region,
                            'subregion': subregion,
                            'population': population,
                            'timezone': timezone,
                            'feature_code': feature_code,
                        }
                    )

                    self.stdout.write(f'Processed: {name}')

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error processing row {row}: {str(e)}'))