"""Bounded local HTTP read-load probe; disposable PostgreSQL database only."""
import os, time, json, shutil, threading, logging
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
# Synthetic load must never report to the real error tracker (load_dotenv does not override this).
os.environ['SENTRY_DSN'] = ''
import django
import django.utils.timezone
django.setup()
from django.conf import settings
from django.db import connection, connections
from django.test import Client
from django.core.wsgi import get_wsgi_application
from load_bench_app import apply_overrides, timed
logging.disable(logging.CRITICAL)
original = connection.settings_dict['NAME']
test_name = 'test_btbs_load_' + time.strftime('%Y%m%d%H%M%S')
apply_overrides(test_name)
connection.settings_dict['TEST']['NAME'] = test_name
disk_root = os.getenv('LOAD_REPORT_DIR', 'C:/' if os.name == 'nt' else '/tmp')
report = {'database': test_name, 'free_before': shutil.disk_usage(disk_root).free, 'stages': []}
server = None
gunicorn = None
created = False
stages = tuple(int(n) for n in os.getenv('LOAD_STAGES', '1,5,20,50,100').split(','))
assert stages and all(1 <= n <= 100 for n in stages)
try:
    connection.creation.create_test_db(verbosity=0, autoclobber=False, serialize=False)
    created = True
    assert connection.settings_dict['NAME'] == test_name and test_name != original
    from accounts.models import User
    from courses.models import Course, CourseRun, Enrollment
    from learning.models import Module, Lesson, Step
    # LOAD_ACTIVITIES=1 adds a quiz and an assignment step to every lesson plus a
    # checkpoint quiz per course, and gives every student a finished attempt and a
    # graded submission, so dashboard/deadline code paths are exercised.
    activities = os.getenv('LOAD_ACTIVITIES') == '1'
    report['activities'] = activities
    from assessment.models import Quiz, Assignment, QuizAttempt, Submission
    from courses.models import RunCheckpoint
    courses, first_activity = [], {}
    for n in range(10):
        c = Course.objects.create(title=f'Load course {n}', is_published=True)
        r = CourseRun.objects.create(course=c)
        m = Module.objects.create(course=c, title='Module', is_published=True)
        for j in range(10):
            l = Lesson.objects.create(course=c, module=m, title=f'Lesson {j}', position=j+1, is_published=True)
            Step.objects.create(lesson=l, title='Text', content='Learning content. '*100, is_published=True)
            if activities:
                q = Quiz.objects.create(course=c, title=f'Quiz {j}', is_published=True)
                a = Assignment.objects.create(course=c, title=f'Task {j}', is_published=True)
                Step.objects.create(lesson=l, title='Quiz', kind='quiz', quiz=q, position=2, is_published=True)
                Step.objects.create(lesson=l, title='Task', kind='assignment', assignment=a, position=3, is_published=True)
                first_activity.setdefault(c.pk, (q, a))
        if activities:
            RunCheckpoint.objects.create(run=r, kind='weekly', period=1,
                                         quiz=Quiz.objects.create(course=c, title='Checkpoint', is_published=True))
        courses.append((c,r))
    cookies = []
    for n in range(max(stages)):
        u = User.objects.create(username=f'load_student_{n}', role='student', password='!')
        enrollments = Enrollment.objects.bulk_create([Enrollment(student=u,course=c,run=r) for c,r in courses])
        if activities:
            QuizAttempt.objects.bulk_create([QuizAttempt(enrollment=e, student=u, quiz=first_activity[e.course_id][0], attempt_no=1,
                deadline_at=django.utils.timezone.now(), status='finished', score=4, max_score=5) for e in enrollments])
            Submission.objects.bulk_create([Submission(enrollment=e, student=u, assignment=first_activity[e.course_id][1],
                attempt_no=1, status='graded', score=80) for e in enrollments])
        client = Client(); client.force_login(u)
        cookies.append('sessionid=' + client.cookies['sessionid'].value)
    c,r = courses[0]
    paths = ['/api/auth/me/', '/api/courses/', '/api/courses/my-learning/', f'/api/learning/courses/{c.pk}/structure/?run_id={r.pk}']
    from django.test.utils import CaptureQueriesContext
    report['endpoint_queries'] = {}
    report['endpoint_profile'] = {}
    for path in paths:
        started = time.perf_counter()
        with CaptureQueriesContext(connection) as captured:
            response = client.get(path)
        assert response.status_code == 200
        report['endpoint_queries'][path] = len(captured)
        report['endpoint_profile'][path] = {
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 2),
            'sql_ms': round(sum(float(q['time']) for q in captured) * 1000, 2),
        }
    print(json.dumps(report['endpoint_queries']), flush=True)
    import cProfile, pstats
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(5):
        for path in paths:
            assert client.get(path).status_code == 200
    profiler.disable()
    if os.getenv('LOAD_REPORT_DIR'):
        with (Path(disk_root) / (test_name + '-profile.txt')).open('w') as output:
            pstats.Stats(profiler, stream=output).strip_dirs().sort_stats('cumulative').print_stats(45)
    connections.close_all()
    threads = int(os.getenv('LOAD_THREADS', '8'))
    assert 1 <= threads <= 32
    report['server_threads'] = threads
    import subprocess, sys
    if os.getenv('LOAD_SERVER') == 'gunicorn':
        # Same gunicorn.conf.py as the container; only the app, port and pool sizes differ.
        workers = int(os.getenv('LOAD_WORKERS', '4'))
        assert 1 <= workers <= 16
        report['server'] = f'gunicorn gthread {workers}x{threads}'
        gunicorn = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--bind', f"{os.getenv('LOAD_BIND', '127.0.0.1')}:18765",
            '--workers', str(workers), '--threads', str(threads), 'load_bench_wsgi:application'],
            cwd=Path(__file__).parent, env={**os.environ, 'LOAD_DB_NAME': test_name})
    else:
        from waitress import create_server
        report['server'] = f'waitress {threads} threads'
        server = create_server(timed(get_wsgi_application()), host=os.getenv('LOAD_BIND', '127.0.0.1'), port=18765, threads=threads)
        threading.Thread(target=server.run, daemon=True).start()
    # Generator has its own interpreter: it cannot contend for the server GIL.
    generated = subprocess.run([sys.executable, str(Path(__file__).with_name('load_http_worker.py'))],
        input=json.dumps({'cookies': cookies, 'paths': paths, 'stages': [] if os.getenv('LOAD_PROFILE_ONLY') else stages,
            'seconds': int(os.getenv('LOAD_SECONDS', '15')), 'disk_root': disk_root,
            'url': os.getenv('LOAD_BASE_URL', 'http://127.0.0.1:18765')}),
        text=True, capture_output=True, timeout=600, check=True)
    report.update(json.loads(generated.stdout))
    report['generator'] = 'separate Python process, same machine/container'
    print(json.dumps(report['stages']), flush=True)
    with connection.cursor() as cur:
        cur.execute('SELECT pg_database_size(current_database())'); report['test_database_bytes']=cur.fetchone()[0]
finally:
    if server:
        server.close(); server.task_dispatcher.shutdown()
    if gunicorn:
        gunicorn.terminate()
        try:
            gunicorn.wait(timeout=40)
        except Exception:
            gunicorn.kill()
    connections.close_all()
    if created:
        # Waitress thread-local persistent connections can outlive dispatcher shutdown.
        # Terminate only this run's disposable database connections, never the LMS DB.
        assert test_name.startswith('test_btbs_load_') and test_name != original
        with connection._nodb_cursor() as cursor:
            cursor.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()', [test_name])
        connection.creation.destroy_test_db(original,verbosity=0)
        report['test_database_removed']=True
    report['free_after']=shutil.disk_usage(disk_root).free
    report['cache_backend'] = settings.CACHES['default']['BACKEND']
    target=Path(__file__).resolve().parents[1]/('LOAD_PROFILE.json' if os.getenv('LOAD_PROFILE_ONLY') else 'LOAD_TEST_REDIS_100.json' if settings.LMS_REDIS_URL and 100 in stages else 'LOAD_TEST_100.json' if 100 in stages else 'LOAD_TEST_AFTER.json')
    if os.getenv('LOAD_REPORT_DIR'):
        target = Path(os.environ['LOAD_REPORT_DIR']) / (test_name + '.json')
    report['route'] = os.getenv('LOAD_BASE_URL', 'http://127.0.0.1:18765')
    report['scenario'] = f'Authenticated GET only, 10 courses x 10 lessons, {max(stages)} student sessions, no browser/media/login hashing load'
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Report saved; disposable database cleanup finished.',flush=True)
