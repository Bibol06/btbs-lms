from django.db import migrations


def forwards(apps, schema_editor):
    Course = apps.get_model('courses', 'Course')
    Run = apps.get_model('courses', 'CourseRun')
    Member = apps.get_model('courses', 'CourseMember')
    Enrollment = apps.get_model('courses', 'Enrollment')
    Module = apps.get_model('learning', 'Module')
    Step = apps.get_model('learning', 'Step')
    StepProgress = apps.get_model('learning', 'StepProgress')
    Lesson = apps.get_model('learning', 'Lesson')
    Material = apps.get_model('learning', 'LessonMaterial')
    for course in Course.objects.all():
        run, _ = Run.objects.get_or_create(course_id=course.id, kind='self_paced', defaults={'title': 'Самостоятельное обучение'})
        if course.teacher_id:
            Member.objects.get_or_create(course_id=course.id, user_id=course.teacher_id, defaults={'role': 'owner'})
        Enrollment.objects.filter(course_id=course.id).update(run_id=run.id)
        module, _ = Module.objects.get_or_create(course_id=course.id, position=1, defaults={'title': 'Основная программа', 'is_published': True})
        for lesson in Lesson.objects.filter(course_id=course.id):
            lesson.module_id = module.id
            lesson.save(update_fields=['module'])
            position = 1
            Step.objects.create(lesson_id=lesson.id, title=lesson.title, content=lesson.content, kind='text', position=position, is_published=lesson.is_published)
            if lesson.video_url:
                position += 1
                Step.objects.create(lesson_id=lesson.id, title='Видео', kind='video', video_url=lesson.video_url, position=position, is_published=lesson.is_published)
            for material in Material.objects.filter(lesson_id=lesson.id):
                position += 1
                Step.objects.create(lesson_id=lesson.id, title=material.title, kind='file', material_id=material.id, position=position, is_published=lesson.is_published)
    for model_name, source in [('Submission', 'assignment'), ('QuizAttempt', 'quiz'), ('LessonProgress', 'lesson')]:
        Model = apps.get_model('assessment', model_name)
        for row in Model.objects.select_related(source).all():
            course_id = getattr(row, source).course_id
            run = Run.objects.get(course_id=course_id, kind='self_paced')
            enrollment, _ = Enrollment.objects.get_or_create(course_id=course_id, run_id=run.id, student_id=row.student_id)
            row.enrollment_id = enrollment.id
            fields = ['enrollment']
            if model_name == 'Submission' and row.score is not None:
                row.status = 'graded'
                fields.append('status')
            row.save(update_fields=fields)
            if model_name == 'LessonProgress':
                for step_id in Step.objects.filter(lesson_id=row.lesson_id, kind__in=['text', 'video', 'file']).values_list('id', flat=True):
                    StepProgress.objects.get_or_create(enrollment_id=enrollment.id, step_id=step_id)


class Migration(migrations.Migration):
    dependencies = [('learning', '0002_module_lesson_module_step_stepprogress_and_more'),
                    ('courses', '0003_enrollment_last_step_enrollment_status_and_more'),
                    ('assessment', '0003_activityschedule_run_gradereview_reviewer_and_more')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
