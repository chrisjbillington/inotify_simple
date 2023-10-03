
from unittest import TestCase
import tempfile
import shutil
from pathlib import Path

from inotify_simple import INotify
from inotify_simple import flags

class TestInotify(TestCase):

    def setUp(self) -> None:
        # Generate a unique temporary directory for each test case
        self.tmp_dir = Path(tempfile.mkdtemp()).resolve()
        # Everything will need an instance, so just make one
        self.inotify = INotify()
        # For tracking watches for cleanup
        self.watches = []
        return super().setUp()

    def tearDown(self) -> None:
        # Ensure all watches are cleaned up
        for watch in self.watches:
            self.inotify.rm_watch(watch)
        # Clean up temporary directory
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        self.inotify.close()
        return super().tearDown()

    def add_watch(self, path, mask) -> None:
        """
        Helper to track watches for ensuring removal at the end of a test
        """
        self.watches.append(self.inotify.add_watch(path, mask))

    def all_events(self):
        """
        Helper to get all the events
        """
        return [event for event in self.inotify.read()]

    def test_access(self):
        # Create file first
        file = self.tmp_dir / "test.txt"
        file.write_text("hello")

        # Setup watch
        self.add_watch(self.tmp_dir, mask=flags.ACCESS)

        # Trigger event
        file.read_text()
        events = self.all_events()

        # Verify
        self.assertEqual(len(events), 1)
        event = events[0]

        self.assertEqual(event.name, "test.txt")
        self.assertEqual(event.mask, flags.ACCESS)

    def test_modify(self):
        # Create file first
        file = self.tmp_dir / "test.txt"
        file.write_text("hello")

        # Setup watch
        self.add_watch(self.tmp_dir, mask=flags.MODIFY)

        # Trigger event
        file.write_bytes(b"hello this way")
        events = self.all_events()

        # Verify
        self.assertEqual(len(events), 1)
        event = events[0]

        self.assertEqual(event.name, "test.txt")
        self.assertEqual(event.mask, flags.MODIFY)

    def test_attrib(self):
        # Create file first
        file = self.tmp_dir / "test.txt"
        file.touch()

        # Setup watch
        self.add_watch(self.tmp_dir, mask=flags.ATTRIB)

        # Trigger event
        file.chmod(0o444)
        events = self.all_events()

        # Verify
        self.assertEqual(len(events), 1)
        event = events[0]

        self.assertEqual(event.name, "test.txt")
        self.assertEqual(event.mask, flags.ATTRIB)

    def test_close_write(self):
        # Create file first
        file = self.tmp_dir / "test.txt"

        # Setup watch
        self.add_watch(self.tmp_dir, mask=flags.CLOSE_WRITE)

        # Trigger event
        file.write_text("close write test")
        events = self.all_events()

        # Verify
        self.assertEqual(len(events), 1)
        event = events[0]

        self.assertEqual(event.name, "test.txt")
        self.assertEqual(event.mask, flags.CLOSE_WRITE)

    def test_access_with_open(self):
        # Create file first
        file = self.tmp_dir / "test.txt"
        file.write_text("hello")

        # Setup watch
        self.add_watch(self.tmp_dir, mask=flags.ACCESS | flags.OPEN)

        # Trigger event
        file.read_text()
        events = self.all_events()

        # Verify
        self.assertEqual(len(events), 2)
        event_open = events[0]
        event_access = events[1]

        self.assertEqual(event_open.name, "test.txt")
        self.assertEqual(event_open.mask, flags.OPEN)
        self.assertEqual(event_access.name, "test.txt")
        self.assertEqual(event_access.mask, flags.ACCESS)

    def test_move_events(self):
        dir1 = self.tmp_dir / "dir1"
        dir1.mkdir()
        file1 = dir1 / "test1.txt"
        file1.touch()

        dir2 = self.tmp_dir / "dir2"
        dir2.mkdir()

        self.add_watch(dir1, mask=flags.MOVED_FROM)
        self.add_watch(dir2, flags.MOVED_TO)

        # File moves from dir1 to dir2
        shutil.move(file1, dir2)

        events = self.all_events()

        self.assertEqual(len(events), 2)
        event_moved_from = events[0]
        event_moved_to = events[1]

        self.assertEqual(event_moved_from.name, "test1.txt")
        self.assertEqual(event_moved_from.mask, flags.MOVED_FROM)
        self.assertEqual(event_moved_to.name, "test1.txt")
        self.assertEqual(event_moved_to.mask, flags.MOVED_TO)