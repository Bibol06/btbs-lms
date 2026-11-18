from django.db import models


class CodeProblem(models.Model):
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    statement = models.TextField()
    starter_code = models.TextField(blank=True)
    max_attempts = models.PositiveIntegerField(default=20)
    # Practice screen: background ("what is already prepared"), a short checklist of
    # what to do, and hints the learner can reveal one by one.
    context = models.TextField(blank=True)
    instructions = models.JSONField(default=list, blank=True)
    hints = models.JSONField(default=list, blank=True)


class TestCase(models.Model):
    problem = models.ForeignKey(CodeProblem, on_delete=models.CASCADE, related_name='test_cases')
    stdin = models.TextField(blank=True)
    expected = models.TextField(blank=True)
    is_sample = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['position', 'id']


class CodeSubmission(models.Model):
    problem = models.ForeignKey(CodeProblem, on_delete=models.CASCADE, related_name='submissions')
    enrollment = models.ForeignKey('courses.Enrollment', on_delete=models.CASCADE)
    code = models.TextField()
    status = models.CharField(max_length=20, default='running')
    passed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    details = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
