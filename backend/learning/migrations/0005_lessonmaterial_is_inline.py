from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('learning', '0004_alter_lesson_module_alter_step_assignment_and_more')]
    operations = [migrations.AddField(model_name='lessonmaterial', name='is_inline', field=models.BooleanField(default=False))]
