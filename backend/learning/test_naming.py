from django.test import SimpleTestCase

from .naming import readable_title


class ReadableTitleTests(SimpleTestCase):
    """QA-041: an upload without a title must not show the raw file name to learners."""

    def test_cleans_extension_underscores_and_quality_tags(self):
        self.assertEqual(readable_title('Уроки_Python_с_нуля_#1 – Программирование (360p, h264).mp4'), 'Уроки Python с нуля #1 – Программирование')
        self.assertEqual(readable_title('lecture_02_[1080p]_x264.webm'), 'lecture 02')
        self.assertEqual(readable_title('Слайды лекции.pdf'), 'Слайды лекции')

    def test_keeps_meaningful_text_and_falls_back(self):
        self.assertEqual(readable_title('HD.mp4'), 'HD')
        self.assertEqual(len(readable_title('a' * 300 + '.pdf')), 200)
