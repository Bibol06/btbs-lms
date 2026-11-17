"""Index review on school-scale data: EXPLAIN ANALYZE every SELECT of the main pages.

Creates a disposable test_btbs_explain_* database, fills it with bulk data
(EXPLAIN_STUDENTS students, default 2000), requests the main student, teacher
and admin endpoints, runs EXPLAIN (ANALYZE, BUFFERS) for each captured SELECT
and reports the slowest queries and sequential scans of large tables. The
database is dropped at the end. Never touches the working LMS database.

  .venv/Scripts/python.exe explain_probe.py            # report -> ../.local/explain/<db>.json
"""
import json
import os
import random
import time
from datetime import timedelta
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['SENTRY_DSN'] = ''
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402
from django.db import connection, connections  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.utils import timezone  # noqa: E402

from load_bench_app import apply_overrides  # noqa: E402

STUDENTS = int(os.getenv('EXPLAIN_STUDENTS', '2000'))
COURSES, MODULES, LESSONS, PER_STUDENT = 20, 4, 5, 5
LARGE = 5000  # a sequential scan of a table with more rows than this is reported
original = connection.settings_dict['NAME']
test_name = 'test_btbs_explain_' + time.strftime('%Y%m%d%H%M%S')
apply_overrides('test_btbs_load_' + test_name)
settings.ALLOWED_HOSTS = ['testserver']
connection.settings_dict['TEST']['NAME'] = test_name
report = {'database': test_name, 'students': STUDENTS}
created = False
rng = random.Random(7)
now = timezone.now()


def bulk(model, rows):
    model.objects.bulk_create(rows, batch_size=5000)
    return len(rows)


def build():
    from accounts.models import User
    from analytics.models import ActivityEvent, AttendanceDay, ProgressSnapshot, SessionRecord
    from assessment.models import Assignment, LessonProgress, Quiz, QuizAttempt, Submission
    from communication.models import Event, Notification
    from courses.models import Course, CourseRun, Enrollment
    from learning.models import Lesson, Module, Step, StepProgress
    counts = {}
    teachers = [User.objects.create(username=f'teacher_{n}', role='teacher', password='!') for n in range(5)]
    admin = User.objects.create(username='admin_0', role='admin', password='!', is_staff=True, is_superuser=True)
    plan = []  # per course: runs, ordered steps with lesson/quiz/assignment
    for n in range(COURSES):
        course = Course.objects.create(title=f'Course {n}', is_published=True, teacher=teachers[n % 5])
        runs = [CourseRun.objects.create(course=course)] + [
            CourseRun.objects.create(course=course, kind='cohort', title=f'Group {g}') for g in range(2)]
        steps, lessons = [], []
        for m in range(MODULES):
            module = Module.objects.create(course=course, title=f'Module {m}', position=m + 1, is_published=True)
            for j in range(LESSONS):
                lesson = Lesson.objects.create(course=course, module=module, title=f'L{m}.{j}', position=m * LESSONS + j + 1, is_published=True)
                quiz = Quiz.objects.create(course=course, title=f'Q{m}.{j}', is_published=True)
                task = Assignment.objects.create(course=course, title=f'A{m}.{j}', is_published=True,
                                                 due_at=now + timedelta(days=rng.randint(-20, 30)))
                steps.append((lesson, Step.objects.create(lesson=lesson, title='Text', content='Text. ' * 50, position=1, is_published=True), None, None))
                steps.append((lesson, Step.objects.create(lesson=lesson, title='Quiz', kind='quiz', quiz=quiz, position=2, is_published=True), quiz, None))
                steps.append((lesson, Step.objects.create(lesson=lesson, title='Task', kind='assignment', assignment=task, position=3, is_published=True), None, task))
                lessons.append(lesson)
        plan.append((course, runs, steps, lessons))
    users = User.objects.bulk_create([User(username=f'student_{n}', role='student', password='!') for n in range(STUDENTS)], batch_size=5000)
    enrollments = []
    for user in users:
        for course, runs, _, _ in rng.sample(plan, PER_STUDENT):
            enrollments.append(Enrollment(student=user, course=course, run=rng.choice(runs)))
    enrollments = Enrollment.objects.bulk_create(enrollments, batch_size=5000)
    by_course = {p[0].id: p for p in plan}
    step_rows, lesson_rows, submissions, attempts, events, snapshots = [], [], [], [], [], []
    for e in enrollments:
        _, _, steps, lessons = by_course[e.course_id]
        done = rng.randint(0, len(steps))
        for lesson, step, quiz, task in steps[:done]:
            step_rows.append(StepProgress(enrollment=e, step=step))
            if quiz:
                attempts.append(QuizAttempt(enrollment=e, student_id=e.student_id, quiz=quiz, attempt_no=1, status='finished',
                                            deadline_at=now, finished_at=now, score=rng.randint(0, 5), max_score=5))
            if task:
                submissions.append(Submission(enrollment=e, student_id=e.student_id, assignment=task, attempt_no=1,
                                              status=rng.choice(['graded'] * 8 + ['submitted', 'returned']), score=rng.randint(40, 100),
                                              review_due_at=now + timedelta(hours=rng.randint(-48, 48))))
        lesson_rows += [LessonProgress(enrollment=e, student_id=e.student_id, lesson=lesson) for lesson in lessons[:done // 3]]
        events += [ActivityEvent(user_id=e.student_id, enrollment=e, run_id=e.run_id, kind=rng.choice(['step_completed', 'step_viewed', 'quiz_finished']),
                                 actor_role='student', occurred_at=now - timedelta(minutes=rng.randint(0, 60 * 24 * 60))) for _ in range(30)]
        snapshots += [ProgressSnapshot(enrollment=e, completed=min(k * 6, len(steps)), total=len(steps), program_fingerprint='x',
                                       captured_at=now - timedelta(days=10 - k)) for k in range(10)]
    counts['step_progress'] = bulk(StepProgress, step_rows)
    counts['lesson_progress'] = bulk(LessonProgress, lesson_rows)
    counts['submissions'] = bulk(Submission, submissions)
    counts['quiz_attempts'] = bulk(QuizAttempt, attempts)
    counts['activity_events'] = bulk(ActivityEvent, events)
    counts['progress_snapshots'] = bulk(ProgressSnapshot, snapshots)
    counts['attendance_days'] = bulk(AttendanceDay, [AttendanceDay(user=u, date=(now - timedelta(days=d)).date(), first_seen_at=now, last_seen_at=now,
                                                                 login_count=1, platform_active=True) for u in users for d in range(60) if rng.random() < 0.6])
    counts['sessions'] = bulk(SessionRecord, [SessionRecord(user=u, key_digest=f'{u.id}-{k}', expires_at=now + timedelta(days=1), browser='Chrome',
                                                            os='Windows', device='desktop', started_at=now - timedelta(days=k)) for u in users for k in range(10)])
    students_of = {}
    for e in enrollments:
        students_of.setdefault(e.course_id, []).append(e.student_id)
    notes = []
    for course, runs, _, _ in plan:
        for k in range(20):
            event = Event.objects.create(key=f'{course.id}-{k}', kind='announcement', course=course, run=runs[0], title='News', target='#')
            notes += [Notification(event=event, recipient_id=s, read_at=now if rng.random() < 0.7 else None) for s in students_of[course.id]]
    counts['notifications'] = bulk(Notification, notes)
    counts['enrollments'] = len(enrollments)
    student = max(users[:50], key=lambda u: sum(1 for e in enrollments if e.student_id == u.id))
    first = next(e for e in enrollments if e.student_id == student.id)
    return counts, student, teachers[0], admin, first, plan[0]


def plan_nodes(node):
    yield node
    for child in node.get('Plans', []):
        yield from plan_nodes(child)


def explain(sql):
    with connection.cursor() as cursor:
        cursor.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql)
        result = cursor.fetchone()[0]
    result = result[0] if isinstance(result, list) else json.loads(result)[0]
    seq = [{'table': n['Relation Name'], 'rows_removed': n.get('Rows Removed by Filter', 0), 'filter': n.get('Filter', '')}
           for n in plan_nodes(result['Plan']) if n['Node Type'] == 'Seq Scan' and reltuples.get(n['Relation Name'], 0) > LARGE]
    return round(result['Execution Time'], 2), seq


try:
    connection.creation.create_test_db(verbosity=0, autoclobber=False, serialize=False)
    created = True
    assert connection.settings_dict['NAME'] == test_name != original
    started = time.time()
    counts, student, teacher, admin, enrollment, (course, runs, steps, _) = build()
    report['rows'] = counts
    report['build_seconds'] = round(time.time() - started)
    with connection.cursor() as cursor:
        cursor.execute('ANALYZE')
        cursor.execute("SELECT relname, reltuples FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace")
        reltuples = dict(cursor.fetchall())
    c, r = enrollment.course_id, enrollment.run_id
    teacher_course, teacher_run = course.id, runs[1].id
    pages = {
        student: ['/api/courses/', '/api/courses/my-learning/', '/api/study/agenda/', f'/api/learning/courses/{c}/structure/?run_id={r}',
                  f'/api/study/courses/{c}/?run_id={r}', '/api/communication/notifications/', '/api/workspace/home/'],
        teacher: ['/api/courses/teacher/', '/api/study/review-queue/', f'/api/study/courses/{teacher_course}/report/?run_id={teacher_run}',
f'/api/courses/runs/{teacher_run}/learning-plan/',
                  f'/api/analytics/dashboard/?run_id={teacher_run}', '/api/workspace/home/'],
        admin: ['/api/study/management/overview/', '/api/study/management/students/', '/api/study/management/courses/',
                '/api/analytics/dashboard/', '/api/analytics/attendance/'],
    }
    endpoints, slow, seq_scans = {}, [], {}
    for user, paths in pages.items():
        client = Client()
        client.force_login(user)
        for path in paths:
            client.get(path)  # warm caches the way a returning user would
            with CaptureQueriesContext(connection) as captured:
                began = time.perf_counter()
                status = client.get(path).status_code
                elapsed = round((time.perf_counter() - began) * 1000)
            key = f'{user.username.split("_")[0]} {path}'
            total = 0.0
            for query in captured.captured_queries:
                sql = query['sql']
                if not sql.lstrip().upper().startswith('SELECT'):
                    continue
                ms, seq = explain(sql)
                total += ms
                slow.append({'endpoint': key, 'ms': ms, 'sql': sql[:600]})
                for scan in seq:
                    entry = seq_scans.setdefault((scan['table'], scan['filter'][:200]), {'table': scan['table'], 'filter': scan['filter'][:200], 'hits': 0, 'max_ms': 0, 'endpoints': set()})
                    entry['hits'] += 1
                    entry['max_ms'] = max(entry['max_ms'], ms)
                    entry['endpoints'].add(key)
            endpoints[key] = {'status': status, 'queries': len(captured), 'response_ms': elapsed, 'explain_ms': round(total, 1)}
    report['endpoints'] = endpoints
    report['slowest'] = sorted(slow, key=lambda q: -q['ms'])[:25]
    report['seq_scans_large_tables'] = sorted(({**v, 'endpoints': sorted(v['endpoints'])} for v in seq_scans.values()), key=lambda v: -v['max_ms'])
    report['table_rows'] = {k: int(v) for k, v in sorted(reltuples.items(), key=lambda kv: -kv[1])[:20]}
finally:
    connections.close_all()
    if created:
        assert test_name.startswith('test_btbs_explain_') and test_name != original
        with connection._nodb_cursor() as cursor:
            cursor.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()', [test_name])
        connection.creation.destroy_test_db(original, verbosity=0)
        report['test_database_removed'] = True
    out = Path(__file__).resolve().parents[1] / '.local' / 'explain'
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{test_name}.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    print(out / f'{test_name}.json')
