import asyncio
import collections
import functools
import shutil
import tempfile
import time
import traceback
import os
import pathlib
import webbrowser

import aiohttp
import aiohttp.web
import appdirs
import yaqd_core

logger = yaqd_core.logging.getLogger(__name__)
logger.setLevel(yaqd_core.logging.INFO)

UploadItem = collections.namedtuple(
    "UploadItem", "kind name path parent client_id", defaults=[None]
)


def refresh_oauth(func):
    @functools.wraps(func)
    async def inner(self, *args, **kwargs):
        res = await func(self, *args, **kwargs)
        if res.status != 401:
            return res
        self._access_token = None
        try:
            await self._use_refresh_token()
        except:
            await self._authorize()

        return await func(self, *args, **kwargs)

    return inner


class GDrive(yaqd_core.Base):
    _kind = "gdrive"
    defaults = {
        "scopes": ["https://www.googleapis.com/auth/drive.file"],
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://www.googleapis.com/oauth2/v4/token",
        "create_file_url": "https://www.googleapis.com/upload/drive/v3/files",
        "generate_ids_url": "https://www.googleapis.com/drive/v3/files/generateIds",
        "update_file_url": "https://www.googleapis.com/upload/drive/v3/files/",  # Needs fileId
        "download_url": "https://drive.google.com/uc?id=",  # Needs fileId
        "open_url": "https://drive.google.com/open?id=",  # Needs fileId
    }

    def __init__(self, name, config, config_filepath):
        self._http_session = aiohttp.ClientSession()
        self._upload_queue = []
        self._copy_queue = []
        self._id_mapping = {}
        self._free_ids = []
        self._access_token = None
        self._refresh_token = None
        super().__init__(name, config, config_filepath)
        self._client_secret = config["client_secret"]
        self._client_id = config["client_id"]
        self._root_folder_id = config["root_folder_id"]
        self._scopes = config["scopes"]
        self._authorization_url = config["authorization_url"]
        self._token_url = config["token_url"]
        self._create_file_url = config["create_file_url"]
        self._generate_ids_url = config["generate_ids_url"]
        self._update_file_url = config["update_file_url"]
        self._download_url = config["download_url"]
        self._open_url = config["open_url"]
        self._loop.create_task(self._stock_ids())
        self._loop.create_task(self._upload())
        self._loop.create_task(self._copy())
        self._cache_dir = pathlib.Path(appdirs.user_cache_dir("yaqd-gdrive", "yaqd")) / "uploads"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _auth_header(self):
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _authorize(self):
        code = asyncio.Future()
        port = 39202
        url = f"{self._authorization_url}?scope={'%20'.join(self._scopes)}&response_type=code&redirect_uri=http://127.0.0.1:{port}&client_id={self._client_id}"
        app = aiohttp.web.Application()

        async def complete_auth(request):
            nonlocal code, url
            if "code" in request.query:
                code.set_result(request.query["code"])
                return aiohttp.web.Response(text="Authorization complete")
            else:
                return aiohttp.web.Response(
                    text=f"Authorization failed\n{request.query.get('error', '')}\n{url}"
                )

        app.add_routes([aiohttp.web.get("/", complete_auth)])

        webbrowser.open(url)

        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        code = await code
        await runner.cleanup()
        await self._obtain_token(code)

    async def _obtain_token(self, code):
        async with self._http_session.post(
            self._token_url,
            json={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": "http://127.0.0.1:39202",
                "grant_type": "authorization_code",
            },
        ) as res:
            logger.debug(await res.text())
            res.raise_for_status()
            json = await res.json()
            self._access_token = json["access_token"]
            self._refresh_token = json["refresh_token"]

    async def _use_refresh_token(self):
        logger.info("Refreshing token")
        async with self._http_session.post(
            self._token_url,
            json={
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
        ) as res:
            res.raise_for_status()
            self._access_token = (await res.json())["access_token"]
            return res

    @refresh_oauth
    async def _create_file(self, name, parent, file_=None, *, id_=None, mime_type=None):
        # TODO: investigate using resumable uploads instead of multipart
        # May be more reliable
        with aiohttp.MultipartWriter("related") as mpwriter:
            mpwriter.append_json(
                {"name": name, "parents": [parent], "id": id_, "mimeType": mime_type}
            )
            if file_ is not None:
                with open(file_, "rb") as f:
                    # NOTE: Not memory safe
                    mpwriter.append(f.read())
            async with self._http_session.post(
                self._create_file_url,
                headers=self._auth_header,
                params={"uploadType": "multipart"},
                data=mpwriter,
            ) as res:
                logger.debug(await res.text())
                return res

    async def _create_folder(self, name, parent, *, id_=None):
        await self._create_file(
            name, parent, id_=id_, mime_type="application/vnd.google-apps.folder"
        )

    @refresh_oauth
    async def _update_file(self, file_, id_):
        with aiohttp.MultipartWriter("related") as mpwriter:
            mpwriter.append_json({"mimeType": None})
            with open(file_, "rb") as f:
                mpwriter.append(f.read())
            async with self._http_session.patch(
                f"{self._update_file_url}{id_}",
                headers=self._auth_header,
                params={"uploadType": "multipart"},
                data=mpwriter,
            ) as res:
                logger.debug(await res.text())
                return res

    @refresh_oauth
    async def _generate_ids(self, count=128):
        async with self._http_session.get(
            self._generate_ids_url,
            headers=self._auth_header,
            params={"count": count, "space": "drive"},
        ) as res:
            if res.status == 200:
                ids = (await res.json())["ids"]
                self._free_ids += ids
            return res

    def get_state(self):
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "upload_queue": self._upload_queue,
            "copy_queue": self._copy_queue,
            "id_mapping": self._id_mapping,
        }

    def _load_state(self, state):
        self._access_token = state.get("access_token")
        self._refresh_token = state.get("refresh_token")
        upload_queue = state.get("upload_queue", [])
        self._upload_queue = [
            UploadItem(*[None if i == "None" else i for i in item]) for item in upload_queue
        ]
        copy_queue = state.get("copy_queue", [])
        self._copy_queue = [
            UploadItem(*[None if i == "None" else i for i in item]) for item in copy_queue
        ]
        self._id_mapping = state.get("id_mapping", {})

    async def _stock_ids(self):
        while True:
            if len(self._free_ids) < 32:
                await self._generate_ids()
            await asyncio.sleep(0.1)

    async def _get_id(self, client_id=None):
        id_ = self._id_mapping.get(client_id)
        # Avoid popping if id is already reserved
        if id_ is None:
            while not self._free_ids:
                await asyncio.sleep(0.01)
            id_ = self._free_ids.pop(0)
            if client_id is not None:
                self._id_mapping[client_id] = id_
        return id_

    def _dir_enqueue(self, path, queue, parent_id):
        for child in path.iterdir():
            if child.is_dir():
                queue.append(UploadItem("folder_upload", child.name, str(child), parent_id))
            else:
                queue.append(UploadItem("file_create", child.name, str(child), parent_id))

    async def _upload(self):
        while True:
            logger.debug("_upload", len(self._upload_queue))
            while self._upload_queue:
                self._busy = True
                try:
                    item = self._upload_queue[0]
                    path = pathlib.Path(item.path)
                    id_ = await self._get_id(item.client_id)
                    parent = item.parent if item.parent else self._root_folder_id
                    if item.kind == "folder_create":
                        await self._create_folder(item.name, parent, id_=id_)
                    elif item.kind == "folder_upload":
                        await self._create_folder(item.name, parent, id_=id_)
                        self.dir_enqueue(path, self._upload_queue, id_)
                    elif item.kind == "file_create":
                        await self._create_file(item.name, parent, path, id_=id_)
                    elif item.kind == "file_update":
                        await self._update_file(path, id_)
                except FileNotFoundError:
                    self._upload_queue.pop(0)
                except BaseException as e:
                    logger.error(e)
                    self._upload_queue.append(self._upload_queue.pop(0))
                else:
                    try:
                        if str(path).startswith(str(self._cache_dir)):
                            path.unlink()
                    except FileNotFoundError:
                        pass

                    self._upload_queue.pop(0)
                self._busy = False
                await asyncio.sleep(0.01)
            await asyncio.sleep(1)

    async def _copy(self):
        while True:
            while self._copy_queue:
                try:
                    item = self._copy_queue[0]._asdict()
                    path = pathlib.Path(item["path"])
                    if path.is_file():
                        fd, tmp = tempfile.mkstemp(
                            prefix=path.stem, suffix=path.suffix, dir=self._cache_dir
                        )
                        os.close(fd)
                        shutil.copy(path, tmp)
                        item["path"] = tmp
                        self._upload_queue.append(UploadItem(**item))
                    elif item["kind"] == "folder_upload":
                        item["kind"] = "folder_create"
                        id_ = await self._get_id(item["client_id"])
                        if item["client_id"] is None:
                            self._id_mapping[id_] = id_
                            item["client_id"] = id_
                        self._upload_queue.append(UploadItem(**item))
                        self._dir_enqueue(path, self._copy_queue, id_)
                    else:
                        self._upload_queue.append(UploadItem(**item))
                except BaseException as e:
                    logger.error(e)
                    self._copy_queue.append(self._copy_queue.pop(0))
                else:
                    self._copy_queue.pop(0)
                await asyncio.sleep(0.01)
            await asyncio.sleep(1)

    def reserve_id(self, client_id, drive_id=None):
        client_id = str(client_id)
        if drive_id is None:
            drive_id = self._id_mapping.get(client_id)
            if drive_id is None:
                drive_id = self._free_ids.pop(0)
        self._id_mapping[client_id] = drive_id
        return drive_id

    def id_to_open_url(self, id_):
        return f"{self._open_url}{self._id_mapping.get(id_, id_)}"

    def id_to_download_url(self, id_):
        return f"{self._download_url}{self._id_mapping.get(id_, id_)}"

    def create_folder(self, path, parent_id=None, id_=None):
        path = pathlib.Path(path)
        self._upload_queue.append(
            UploadItem(
                "folder_create",
                path.name,
                str(path),
                self._id_mapping.get(parent_id, parent_id),
                id_,
            )
        )

    def upload_folder(self, path, parent_id=None, id_=None):
        path = pathlib.Path(path)
        self._copy_queue.append(
            UploadItem(
                "folder_upload",
                path.name,
                str(path),
                self._id_mapping.get(parent_id, parent_id),
                id_,
            )
        )

    def create_file(self, path, parent_id=None, id_=None):
        path = pathlib.Path(path)
        self._copy_queue.append(
            UploadItem(
                "file_create",
                path.name,
                str(path),
                self._id_mapping.get(parent_id, parent_id),
                id_,
            )
        )

    def update_file(self, path, id_=None):
        path = pathlib.Path(path)
        self._copy_queue.append(UploadItem("file_update", path.name, str(path), None, id_))

    def is_uploaded(self, id_):
        for item in self._copy_queue:
            if item.client_id == id_:
                return False
        for item in self._upload_queue:
            if item.client_id == id_:
                return False
        return True

    def close(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self._http_session.close())
        super().close()


if __name__ == "__main__":
    GDrive.defaults.update(
        {
            "client_id": "943700362860-7fmktmg2rjrblt4v2qh86141l6vg7qju.apps.googleusercontent.com",
            "client_secret": "pKIjNEasosRswlt4xWOxQCpD",
            "root_folder_id": "1oZOabPMoTO2XPE5mWOC_9XOR9PsUgepC",
        }
    )
    gdrive = GDrive("test", GDrive.defaults, "")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(gdrive._generate_ids())
    loop.run_until_complete(gdrive._create_file("test.py", gdrive._root_folder_id, __file__))
