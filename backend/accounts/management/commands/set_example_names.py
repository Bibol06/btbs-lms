from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


EXAMPLE_NAMES = {
    'admin': ('Бибол', 'Жайлыбаев'),
    'demo_admin': ('Арман', 'Мусин'),
    'demo_teacher': ('Алия', 'Сейтенова'),
    'demo_tutor': ('Ерлан', 'Омаров'),
    'demo_student': ('Думан', 'Нурланов'),
    'demo_peer': ('Аружан', 'Садыкова'),
    'teacher01': ('Айгуль', 'Ахметова'),
    'студент 1': ('Алихан', 'Сериков'),
}


class Command(BaseCommand):
    help = 'Fill empty profile names of the known local example accounts; preserve logins and roles.'

    @transaction.atomic
    def handle(self, *args, **options):
        updated = 0
        for user in get_user_model().objects.filter(username__in=EXAMPLE_NAMES):
            if user.first_name.strip() or user.last_name.strip():
                continue
            user.first_name, user.last_name = EXAMPLE_NAMES[user.username]
            user.save(update_fields=['first_name', 'last_name'])
            updated += 1
        self.stdout.write(f'Profiles updated: {updated}')
