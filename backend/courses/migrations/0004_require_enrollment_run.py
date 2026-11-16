from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('courses', '0003_enrollment_last_step_enrollment_status_and_more'), ('learning', '0003_import_legacy_learning')]
    operations = [migrations.AlterField(model_name='enrollment', name='run', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollments', to='courses.courserun'))]
