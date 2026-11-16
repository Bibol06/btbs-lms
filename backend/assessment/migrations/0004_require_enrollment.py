from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('assessment', '0003_activityschedule_run_gradereview_reviewer_and_more'), ('learning', '0003_import_legacy_learning')]
    operations = [migrations.AlterField(model_name=name, name='enrollment', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_records', to='courses.enrollment')) for name in ['submission', 'quizattempt', 'lessonprogress']]
