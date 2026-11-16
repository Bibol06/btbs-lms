from django.contrib import admin
from .models import CodeProblem, TestCase, CodeSubmission


class TestCaseInline(admin.TabularInline):
    model = TestCase
    extra = 1


@admin.register(CodeProblem)
class CodeProblemAdmin(admin.ModelAdmin):
    inlines = [TestCaseInline]


@admin.register(CodeSubmission)
class CodeSubmissionAdmin(admin.ModelAdmin):
    readonly_fields = ['code', 'status', 'passed', 'total', 'details', 'enrollment', 'problem', 'created_at']
