from django.contrib import admin
from .models import Assignment, Submission, Quiz, Question, QuizAttempt, LessonProgress

admin.site.register([Assignment, Submission, Quiz, Question, QuizAttempt, LessonProgress])
