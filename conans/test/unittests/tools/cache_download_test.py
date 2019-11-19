import unittest
from multiprocessing import Process

from conans.client.tools import net
from conans.test.utils.test_files import temp_folder


class CacheDownloadTest(unittest.TestCase):

    def setUp(self):
        self._cache_dir = temp_folder()

    def test_file_is_downloaded_the_first_time(self):
        """Tests file will be downloaded if it does not exist in cache"""
        pass

    def test_file_is_not_downloaded_if_exists_in_cache(self):
        """Tests file will not downloaded if it already exists in cache"""
        pass

    def test_cache_download_with_concurrent_processes(self):
        """Tests if concurrent processes work as expected if they're
        working at the same time"""

        def _download_1():
            net.cache_download('https://github.com/conan-io/conan/archive/1.20.4.zip', 'conan.zip')

        def _downoad_2():
            net.cache_download('https://github.com/conan-io/conan/archive/1.20.4.zip', 'conan.zip')

        p1 = Process(target=_download_1)
        p1.start()
        p2 = Process(target=_downoad_2)
        p2.start()
        p1.join()
        p2.join()

