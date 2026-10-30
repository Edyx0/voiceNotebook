import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from voice_notebook import App


def source(source_id, title):
    return SimpleNamespace(id=source_id, title=title, is_ready=True, is_error=False)


class CourseNotebookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = App(Path(self.tmp.name))
        self.app.config['lectures'] = [{'course': 'EE211'}, {'course': 'TKL201'}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_grouping_requires_an_explicit_assignment_for_ambiguous_alias(self):
        books = [SimpleNamespace(id='a', title='EE211 w2'), SimpleNamespace(id='b', title='ee221 w1'),
                 SimpleNamespace(id='c', title='ee w3'), SimpleNamespace(id='d', title='tkl w2'),
                 SimpleNamespace(id='e', title='CSE211 · All weeks')]
        groups, ambiguous = self.app.course_notebooks.groups(books)
        self.assertEqual(ambiguous, [{'notebook_id': 'c', 'title': 'ee w3', 'courses': ['EE211', 'EE221']}])
        self.assertEqual([b.id for b in groups['TKL201']], ['d'])
        self.app.course_notebooks.assign('c', 'EE211')
        groups, ambiguous = self.app.course_notebooks.groups(books)
        self.assertEqual(ambiguous, [])
        self.assertEqual([b.id for b in groups['EE211']], ['a', 'c'])
        self.assertNotIn('CSE211', groups)

    def test_copy_all_sources_once_and_add_later_sources(self):
        original = SimpleNamespace(id='week', title='EE211 w2')
        books = [original]
        original_sources = [source('audio', 'recording.mp3'), source('photo', 'board.pdf')]
        target_sources = []
        events = []

        async def create(title):
            return SimpleNamespace(id='course', title=title)

        async def list_sources(notebook, **kwargs):
            return list(original_sources if notebook == 'week' else target_sources)

        async def copy(origin, ids, target):
            events.append('copy-' + ids[0])
            item = next(s for s in original_sources if s.id == ids[0])
            copied = source('copy-' + item.id, item.title)
            target_sources.append(copied)
            return [SimpleNamespace(original_id=item.id, source=copied)]

        async def wait(notebook, source_id, **kwargs):
            events.append('wait-' + source_id)
        client = SimpleNamespace(notebooks=SimpleNamespace(list=AsyncMock(return_value=books), create=AsyncMock(side_effect=create)),
            sources=SimpleNamespace(list=AsyncMock(side_effect=list_sources), copy=AsyncMock(side_effect=copy), wait_until_ready=AsyncMock(side_effect=wait)))
        session = AsyncMock()
        session.__aenter__.return_value = client
        with patch('notebooklm.NotebookLMClient.from_storage', return_value=session):
            asyncio.run(self.app.course_notebooks.sync())
            asyncio.run(self.app.course_notebooks.sync())
            original_sources.append(source('new', 'new recording.mp3'))
            asyncio.run(self.app.course_notebooks.sync())
        self.assertEqual(client.notebooks.create.await_count, 1)
        self.assertEqual(client.sources.copy.await_count, 3)
        self.assertEqual(events[:2], ['copy-audio', 'copy-photo'])
        self.assertEqual([s.title for s in target_sources], ['recording.mp3', 'board.pdf', 'new recording.mp3'])
        self.assertEqual(self.app.course_notebooks.records()[0]['notebook_id'], 'course')

    def test_lost_copy_response_is_not_sent_again_and_can_be_reconciled(self):
        item = source('original', 'lecture.mp3')
        existing = []
        client = SimpleNamespace(sources=SimpleNamespace(list=AsyncMock(side_effect=lambda *a, **k: list(existing)),
            copy=AsyncMock(side_effect=TimeoutError('lost response')), wait_until_ready=AsyncMock()))
        with self.assertRaises(TimeoutError):
            asyncio.run(self.app.course_notebooks.copy_source(client, 'EE211', 'week', 'course', item))
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            asyncio.run(self.app.course_notebooks.copy_source(client, 'EE211', 'week', 'course', item))
        existing.append(source('new-id', 'lecture.mp3'))
        pending = asyncio.run(self.app.course_notebooks.copy_source(client, 'EE211', 'week', 'course', item))
        asyncio.run(self.app.course_notebooks.finish_source(client, *pending))
        self.assertEqual(client.sources.copy.await_count, 1)
        client.sources.wait_until_ready.assert_awaited_once_with('course', 'new-id', timeout=1200)

    def test_existing_unowned_destination_is_not_reused(self):
        books = [SimpleNamespace(id='other', title='EE211 · All weeks')]
        client = SimpleNamespace(notebooks=SimpleNamespace(create=AsyncMock()))
        with self.assertRaisesRegex(ValueError, 'already exists'):
            asyncio.run(self.app.course_notebooks.destination(client, books, 'EE211'))
        client.notebooks.create.assert_not_awaited()

    def test_photo_upload_updates_course_notebooks(self):
        with patch.object(self.app.photos, 'sync', new_callable=AsyncMock) as photos, \
             patch.object(self.app.course_notebooks, 'sync', new_callable=AsyncMock) as courses, \
             patch('voice_notebook.threading.Thread', side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            self.app.start('photos-sync', photo_ids=['photo'])
        photos.assert_awaited_once_with(['photo'])
        courses.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
