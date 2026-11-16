
from django.contrib import admin
from .models import Lesson, LessonMaterial, Module, Step

admin.site.register([Module, Step])


class LessonMaterialInline(admin.TabularInline):
    model = LessonMaterial
    extra = 1


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'course',
        'position',
        'is_published'
    )

    list_filter = (
        'course',
        'is_published'
    )

    search_fields = ('title',)

    inlines = [LessonMaterialInline]
