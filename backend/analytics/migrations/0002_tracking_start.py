from django.db import migrations


def start_tracking(apps, schema_editor):
    apps.get_model('analytics', 'TrackingCoverage').objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [('analytics', '0001_initial')]
    operations = [migrations.RunPython(start_tracking, migrations.RunPython.noop)]
