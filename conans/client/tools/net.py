import os
import shutil

from conans.client.rest.uploader_downloader import FileDownloader
from conans.client.tools.files import check_md5, check_sha1, check_sha256, unzip
from conans.errors import ConanException
from conans.util.env_reader import get_env
from conans.util.fallbacks import default_output, default_requester
from conans.util.files import md5
from conans.util.sha import sha256


def get(url, md5='', sha1='', sha256='', destination=".", filename="", keep_permissions=False,
        pattern=None, requester=None, output=None, verify=True, retry=None, retry_wait=None,
        overwrite=False, auth=None, headers=None):
    """ high level downloader + unzipper + (optional hash checker) + delete temporary zip
    """
    if not filename and ("?" in url or "=" in url):
        raise ConanException("Cannot deduce file name form url. Use 'filename' parameter.")

    filename = filename or os.path.basename(url)
    # FIXME: MD5 or SHA1 will not be required anymore. SHA256 == checksum?
    download(url, filename, sha256, out=output, requester=requester, verify=verify, retry=retry,
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


def _get_cached_download_folder(url, filename):
    """Get a MD5 hash code

    :param url: `str` any URL
    :param filename: `str` any file name
    :return: MD5 hash code
    """
    return md5(url + filename)


def _copy_cached_download_to_source(cached_file_path, checksum):
    """Copy cached downloads to current directory (data)

    :param cached_file_path: `str` file path
    :param checksum: `str` SHA256 hash code to check with cached filename
    """

    if check_sha256(cached_file_path, checksum):
        try:
            # Copy cached file to current directory
            shutil.copytree(cached_file_path, '.', symlinks=True)
        except Exception as e:
            msg = str(e)
            if "206" in msg:  # System error shutil.Error 206: Filename or extension too long
                msg += "\nUse short_paths=True if paths too long"
            raise ConanException("%s\nError getting cached files to source folder" % msg)


def download(url, filename, checksum, verify=True, out=None, retry=None, retry_wait=None, overwrite=False,
             auth=None, headers=None, requester=None):

    out = default_output(out, 'conans.client.tools.net.download')
    requester = default_requester(requester, 'conans.client.tools.net.download')

    # It might be possible that users provide their own requester
    retry = retry if retry is not None else getattr(requester, "retry", None)
    retry = retry if retry is not None else 1
    retry_wait = retry_wait if retry_wait is not None else getattr(requester, "retry_wait", None)
    retry_wait = retry_wait if retry_wait is not None else 5

    # Check if downloads cache is enabled or not
    cache_download_is_enabled = get_env("CONAN_DOWNLOADS_CACHE_ENABLED")
    if cache_download_is_enabled:
        cached_folder_path = os.path.join(get_env("CONAN_DOWNLOADS_CACHE_PATH"),
                                          _get_cached_download_folder(url, filename))
        cached_file_path = os.path.join(cached_folder_path, filename)
        # Have a look at local cache downloads folder
        if os.path.exists(cached_file_path):
            _copy_cached_download_to_source(cached_file_path, checksum)
        else:  # Else download and save in cache folder
            downloader = FileDownloader(requester=requester, output=out, verify=verify)
            downloader.download(url, filename, retry=retry, retry_wait=retry_wait,
                                overwrite=overwrite,
                                auth=auth, headers=headers)
            # Create the cache folder
            os.makedirs(cached_folder_path)
            # Copy to filename to cache folder
            shutil.copytree(filename, cached_file_path, symlinks=True)
    else:
        downloader = FileDownloader(requester=requester, output=out, verify=verify)
        downloader.download(url, filename, retry=retry, retry_wait=retry_wait, overwrite=overwrite,
                            auth=auth, headers=headers)
    out.writeln("")
