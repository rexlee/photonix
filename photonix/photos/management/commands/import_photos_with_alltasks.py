from django.core.management.base import BaseCommand

from photonix.photos.utils.organise import import_photos_from_dir
from photonix.photos.utils.system import missing_system_dependencies
from photonix.photos.utils.raw import ensure_raw_processing_tasks, process_raw_tasks
from photonix.photos.utils.thumbnails import process_generate_thumbnails_tasks
from photonix.photos.utils.classification import process_classify_images_tasks
import redis_lock
import redis
import os
from photonix.photos.models import Task
from photonix.photos.utils.classification import ThreadedQueueProcessor


r = redis.Redis(host=os.environ.get('REDIS_HOST', '127.0.0.1'))
num_workers = 4
batch_size = 64


class Command(BaseCommand):
    help = 'Copies all photos from one directory into structured data folder hierchy and creates relevant database records'

    def add_arguments(self, parser):
        parser.add_argument('paths', nargs='+')

    def import_photos(self, paths):
        missing = missing_system_dependencies(['exiftool', ])
        if missing:
            print('Missing dependencies: {}'.format(missing))
            exit(1)

        for path in paths:
            import_photos_from_dir(path, True)

    def handle(self, *args, **options):
        self.import_photos(options['paths'])
        ensure_raw_processing_tasks()
        process_raw_tasks()
        process_generate_thumbnails_tasks()
        redis_lock.reset_all(r)
        process_classify_images_tasks()

        self.handleLocaltion()
        self.handleObject()

    def handleLocaltion(self):
        from photonix.classifiers.location import LocationModel, run_on_photo
        print('Loading object location model')
        model = LocationModel()

        threaded_queue_processor = ThreadedQueueProcessor(
            model, 'classify.location', run_on_photo, num_workers, batch_size)
        threaded_queue_processor.run(loop=False)

    def handleObject(self):
        from photonix.classifiers.object import ObjectModel, run_on_photo
        print('Loading object classification model')
        model = ObjectModel()
        threaded_queue_processor = ThreadedQueueProcessor(
            model, 'classify.object', run_on_photo, num_workers, batch_size)
        threaded_queue_processor.run(loop=False)
