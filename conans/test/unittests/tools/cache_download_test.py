import os
import shutil
import unittest
from multiprocessing import Process

import requests

from conans.test.utils.tools import TestBufferConanOutput

try:
    from unittest.mock import MagicMock, patch
except:
    from mock import MagicMock, patch

from conans.client.tools import net
from conans.test.utils.test_files import temp_folder


class FakeDownloader(MagicMock):

    def download(self, url, file_path, **kwargs):
        """Create a fake file"""
        with open(file_path, "w+") as f:
            f.write("Fake file")


class CacheDownloadTest(unittest.TestCase):

    def setUp(self):
        self._cwd = temp_folder(path_with_spaces=False)
        self._file_path = os.path.join(self._cwd, 'conan.zip')
        self._url = 'https://github.com/conan-io/conan/archive/1.20.4.zip'
        self._cache_dir = temp_folder(path_with_spaces=False)
        net.DOWNLOADS_CACHE_FOLDER = self._cache_dir
        self._cache_folder, self._cached_file_path = \
            net.get_cache_folders_info(self._url, self._file_path)
        self._out = TestBufferConanOutput()

    def tearDown(self):
        shutil.rmtree(self._cwd)
        shutil.rmtree(self._cache_dir)

    @patch('conans.client.tools.net.FileDownloader', new_callable=FakeDownloader)
    def test_file_is_downloaded_the_first_time(self, file_downloader_mock):
        """Tests file will be downloaded if it does not exist in cache"""
        self.assertFalse(os.path.exists(self._cached_file_path))
        net.cache_download(self._url, self._file_path,
                           out=self._out, requester=requests)
        file_downloader_mock.assert_called_once()
        self.assertTrue(os.path.exists(self._cached_file_path))

    @patch('conans.client.tools.net.FileDownloader', new_callable=FakeDownloader)
    def test_file_is_not_downloaded_if_exists_in_cache(self, file_downloader_mock):
        """Tests file will not downloaded if it already exists in cache"""
        os.makedirs(self._cache_folder)
        with open(self._cached_file_path, 'w+') as f:
            f.write("Fake file")

        net.cache_download(self._url, self._file_path,
                           out=self._out, requester=requests)
        file_downloader_mock.assert_not_called()
        self.assertTrue(os.path.exists(self._file_path))

    @patch('conans.client.tools.net.FileDownloader', new_callable=FakeDownloader)
    def test_cache_download_with_concurrent_processes(self, file_downloader_mock):
        """Tests if concurrent processes work as expected if they're
        working at the same time"""

        def _download_1():
            net.cache_download('https://github.com/conan-io/conan/archive/1.20.4.zip', 'conan.zip',
                               out=self._out, requester=requests)

        def _downoad_2():
            net.cache_download('https://github.com/conan-io/conan/archive/1.20.4.zip', 'conan.zip',
                               out=self._out, requester=requests)

        p1 = Process(target=_download_1)
        p1.start()
        p2 = Process(target=_downoad_2)
        p2.start()
        p1.join()
        p2.join()

