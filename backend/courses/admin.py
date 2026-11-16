
from django.contrib import admin
from .models import Course, Enrollment, CourseRun, CourseMember

admin.site.register([CourseRun, CourseMember])


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'teacher',
        'is_published',
        'created_at',
    )

    search_fields = ('title',)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'course',
        'enrolled_at',
    )

    list_filter = ('course',)
