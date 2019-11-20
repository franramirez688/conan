import hashlib
import os
import shutil

from conans.client.rest.uploader_downloader import FileDownloader
from conans.client.tools.files import check_md5, check_sha1, check_sha256, unzip
from conans.errors import ConanException
from conans.util.fallbacks import default_output, default_requester


DOWNLOADS_CACHE_FOLDER = os.path.join(os.path.expanduser('~'), 'conan_downloads_cache')


def get(url, md5='', sha1='', sha256='', destination=".", filename="", keep_permissions=False,
        pattern=None, requester=None, output=None, verify=True, retry=None, retry_wait=None,
        overwrite=False, auth=None, headers=None):
    """ high level downloader + unzipper + (optional hash checker) + delete temporary zip
    """
    if not filename and ("?" in url or "=" in url):
        raise ConanException("Cannot deduce file name form url. Use 'filename' parameter.")

    filename = filename or os.path.basename(url)
    download(url, filename, out=output, requester=requester, verify=verify, retry=retry,
             retry_wait=retry_wait, overwrite=overwrite, auth=auth, headers=headers)

    if md5:
        check_md5(filename, md5)
    if sha1:
        check_sha1(filename, sha1)
    if sha256:
        check_sha256(filename, sha256)

    unzip(filename, destination=destination, keep_permissions=keep_permissions, pattern=pattern,
          output=output)
    os.unlink(filename)


def ftp_download(ip, filename, login='', password=''):
    import ftplib
    try:
        ftp = ftplib.FTP(ip)
        ftp.login(login, password)
        filepath, filename = os.path.split(filename)
        if filepath:
            ftp.cwd(filepath)
        with open(filename, 'wb') as f:
            ftp.retrbinary('RETR ' + filename, f.write)
    except Exception as e:
        try:
            os.unlink(filename)
        except OSError:
            pass
        raise ConanException("Error in FTP download from %s\n%s" % (ip, str(e)))
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def download(url, filename, verify=True, out=None, retry=None, retry_wait=None, overwrite=False,
             auth=None, headers=None, requester=None):

    out = default_output(out, 'conans.client.tools.net.download')
    requester = default_requester(requester, 'conans.client.tools.net.download')

    # It might be possible that users provide their own requester
    retry = retry if retry is not None else getattr(requester, "retry", None)
    retry = retry if retry is not None else 1
    retry_wait = retry_wait if retry_wait is not None else getattr(requester, "retry_wait", None)
    retry_wait = retry_wait if retry_wait is not None else 5

    downloader = FileDownloader(requester=requester, output=out, verify=verify)
    downloader.download(url, filename, retry=retry, retry_wait=retry_wait, overwrite=overwrite,
                        auth=auth, headers=headers)
    out.writeln("")


def get_cache_folders_info(url, filename) -> (str, str):
    """Get the cache folder and cached file path"""
    file_dir, base_file_name = os.path.split(filename)
    # Hashed cache subfolder with MD5 algorithm
    name_to_be_hashed = ("%s%s" % (url, base_file_name)).encode()
    hashed_cache_subfolder = hashlib.md5(name_to_be_hashed).hexdigest()
    # Get cache folder and final cached file path
    cache_folder = os.path.join(DOWNLOADS_CACHE_FOLDER, hashed_cache_subfolder)
    cached_file_path = os.path.join(cache_folder, base_file_name)
    return cache_folder, cached_file_path


def cache_download(url, filename, *args, **kwargs):
    """Cache any download to avoid repeating the same process"""
    cache_folder_path, cached_file_path = get_cache_folders_info(url, filename)
    # Check if file already exists in the cache
    if os.path.exists(cached_file_path):
        shutil.copyfile(cached_file_path, filename)
    else:  # if not, creates the cache folder and copy the file
        os.makedirs(cache_folder_path, exist_ok=True)
        download(url, filename, *args, **kwargs)
        shutil.copyfile(filename, cached_file_path)
