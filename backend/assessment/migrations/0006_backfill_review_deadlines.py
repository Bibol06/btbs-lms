from datetime import timedelta
from django.db import migrations


def backfill(apps, schema_editor):
    Submission = apps.get_model('assessment', 'Submission')
    Schedule = apps.get_model('assessment', 'ActivitySchedule')
    for s in Submission.objects.filter(status='submitted', review_due_at__isnull=True).select_related('assignment', 'enrollment__run__course').iterator():
        run = s.enrollment.run
        settings = Schedule.objects.filter(run_id=run.id, assignment_id=s.assignment_id).first() or s.assignment
        teacher = run.teachers.filter(is_active=True).order_by('id').first()
        if teacher is None:
            teacher = run.course.teacher
            if teacher and not teacher.is_active:
                teacher = None
        s.review_due_at = s.submitted_at + timedelta(hours=settings.review_hours)
        s.reviewer_id = teacher.id if teacher else None
        s.save(update_fields=['review_due_at', 'reviewer_id'])


class Migration(migrations.Migration):
    dependencies = [('assessment', '0005_assignmentextension_activityschedule_allow_late_and_more')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
