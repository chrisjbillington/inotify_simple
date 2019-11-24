import os
from inotify_simple import INotify, flags

os.mkdir('/tmp/inotify_test')

inotify = INotify()
watch_flags = flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF
wd = inotify.add_watch('/tmp/inotify_test', watch_flags)

# Now create, delete and modify some files in the directory being monitored:
os.chdir('/tmp/inotify_test')
# CREATE event for a directory:
os.system('mkdir foo')
# CREATE event for a file:
os.system('echo hello > test.txt')
# MODIFY event for the file:
os.system('echo world >> test.txt')
# DELETE event for the file
os.system('rm test.txt')
# DELETE event for the directory
os.system('rmdir foo')
os.chdir('/tmp')
# DELETE_SELF on the original directory. Also generates an IGNORED event indicating the
# watch was removed.
os.system('rmdir inotify_test')

# And see the corresponding events:
for event in inotify.read():
    print(event)
    for flag in flags.from_mask(event.mask):
        print('    ' + str(flag))
